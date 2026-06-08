import os
from PySide6 import QtWidgets, QtCore, QtGui

from core import AIAgentCore
from houdini_context import HoudiniContext
from settings_dialog import SettingsDialog
from styles import GLOBAL_STYLE
import context_manager

from components import SessionItemWidget, ChatTextBrowser
from workers import AgentWorker
from chat_formatter import build_bubble


class AIAgentUI(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(AIAgentUI, self).__init__(parent)
        self.setWindowTitle("Houdini AI TD Agent")
        self.core = AIAgentCore()
        self.context = HoudiniContext()
        self.last_ai_response = ""
        self.current_user_message = None
        self.current_agent_response = None
        self.first_chunk_received = False
        self.code_blocks_store = {}
        self.action_states = {}
        self.thinking_timer = QtCore.QTimer()
        self.thinking_timer.timeout.connect(self.animate_thinking)
        self.thinking_dots = 0
        # Render Throttle (~30 FPS), auto-stops when idle
        self.render_timer = QtCore.QTimer()
        self.render_timer.setInterval(33)
        self.render_timer.timeout.connect(self._on_render_tick)
        self.needs_render = False
        self._loading_models = False
        self.current_model_display = ""
        self.setStyleSheet(GLOBAL_STYLE)
        self.init_ui()
        self.load_models()
        self.refresh_session_list()
        self.request_render()

    def init_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        # === Left Sidebar ===
        self.sidebar = QtWidgets.QWidget()
        self.sidebar.setObjectName("Sidebar")
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        self.new_chat_btn = QtWidgets.QPushButton("＋ New Chat")
        self.new_chat_btn.setObjectName("NewChatButton")
        self.new_chat_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.new_chat_btn.clicked.connect(self.on_new_chat)
        self.session_scroll = QtWidgets.QScrollArea()
        self.session_scroll.setObjectName("SessionScroll")
        self.session_scroll.setWidgetResizable(True)
        self.session_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.session_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.session_container = QtWidgets.QWidget()
        self.session_container.setObjectName("SessionContainer")
        self.session_layout = QtWidgets.QVBoxLayout(self.session_container)
        self.session_layout.setContentsMargins(10, 0, 10, 0)
        self.session_layout.setSpacing(2)
        self.session_layout.setAlignment(QtCore.Qt.AlignTop)
        self.session_scroll.setWidget(self.session_container)
        sidebar_layout.addWidget(self.new_chat_btn)
        sidebar_layout.addWidget(self.session_scroll)
        # === Right Chat Area ===
        self.chat_area = QtWidgets.QWidget()
        chat_layout = QtWidgets.QVBoxLayout(self.chat_area)
        chat_layout.setContentsMargins(20, 20, 20, 20)
        chat_layout.setSpacing(15)
        top_bar = QtWidgets.QHBoxLayout()
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.model_combo.lineEdit().setPlaceholderText("Search models...")
        self.model_combo.lineEdit().setAlignment(QtCore.Qt.AlignLeft)
        self.model_combo.setMinimumWidth(250)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        completer = QtWidgets.QCompleter()
        completer.setFilterMode(QtCore.Qt.MatchContains)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.model_combo.setCompleter(completer)
        self.settings_btn = QtWidgets.QPushButton("⚙ Settings")
        self.settings_btn.setObjectName("SettingsButton")
        self.settings_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings)
        top_bar.addWidget(self.model_combo)
        top_bar.addStretch()
        top_bar.addWidget(self.settings_btn)
        self.chat_display = ChatTextBrowser()
        self.chat_display.custom_link_clicked.connect(self.handle_link_click)
        self.chat_display.document().setDefaultStyleSheet("")
        # Context Progress Bar (compact, left-aligned)
        ctx_bar = QtWidgets.QHBoxLayout()
        ctx_bar.setContentsMargins(0, 0, 0, 5)
        self.context_progress = QtWidgets.QProgressBar()
        self.context_progress.setObjectName("ContextProgressBar")
        self.context_progress.setTextVisible(True)
        self.context_progress.setFormat("Context: 0 / 50000 tokens")
        self.context_progress.setMinimum(0)
        self.context_progress.setMaximum(50000)
        self.context_progress.setFixedHeight(18)
        self.context_progress.setMaximumWidth(280)
        ctx_bar.addWidget(self.context_progress)
        ctx_bar.addStretch()
        # Command Autocomplete Popup
        self.cmd_popup = QtWidgets.QListWidget()
        self.cmd_popup.setObjectName("CommandPopup")
        self.cmd_popup.addItems([
            "/compact - Force manual context summarization"
        ])
        self.cmd_popup.setFixedHeight(35)
        self.cmd_popup.hide()
        self.cmd_popup.itemClicked.connect(self.on_cmd_popup_selected)
        # Input Area
        input_container = QtWidgets.QFrame()
        input_container.setObjectName("InputContainer")
        input_layout = QtWidgets.QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(0)
        self.text_input = QtWidgets.QTextEdit()
        self.text_input.setObjectName("InputTextEdit")
        self.text_input.setMaximumHeight(100)
        self.text_input.setPlaceholderText("Message AI TD Agent... (Type '/' for commands)")
        self.text_input.installEventFilter(self)
        self.text_input.textChanged.connect(self.on_text_changed)
        self.send_btn = QtWidgets.QPushButton("↑")
        self.send_btn.setObjectName("SendButton")
        self.send_btn.setFixedSize(30, 30)
        self.send_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self.on_send_clicked)
        send_layout = QtWidgets.QVBoxLayout()
        send_layout.addStretch()
        send_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.text_input)
        input_layout.addLayout(send_layout)
        chat_layout.addLayout(top_bar)
        chat_layout.addWidget(self.chat_display, stretch=1)
        chat_layout.addWidget(self.cmd_popup)
        chat_layout.addLayout(ctx_bar)
        chat_layout.addWidget(input_container)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.chat_area)
        splitter.setSizes([250, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

    # --- Autocomplete ---
    def on_text_changed(self):
        text = self.text_input.toPlainText()
        self.cmd_popup.setVisible(text.startswith("/"))

    def on_cmd_popup_selected(self, item):
        cmd = item.text().split(" ")[0]
        self.text_input.setText(cmd)
        cursor = self.text_input.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.text_input.setTextCursor(cursor)
        self.cmd_popup.hide()

    # --- Link Actions ---
    def handle_link_click(self, url_str):
        if url_str.startswith("copy_code:"):
            block_id = url_str[len("copy_code:"):].strip("/")
            if block_id in self.code_blocks_store:
                try:
                    import hou
                    hou.ui.copyTextToClipboard(self.code_blocks_store[block_id])
                except Exception:
                    QtWidgets.QApplication.clipboard().setText(self.code_blocks_store[block_id])
                self.action_states[url_str] = "&nbsp;✅ Copied!&nbsp;"
                self.request_render()
                QtCore.QTimer.singleShot(2000, lambda: self._reset_action(url_str))
        elif url_str.startswith("run_code:"):
            block_id = url_str[len("run_code:"):].strip("/")
            if block_id in self.code_blocks_store:
                success, msg = self.context.execute_code_block(self.code_blocks_store[block_id])
                self.action_states[url_str] = "&nbsp;✅ Success!&nbsp;" if success else "&nbsp;❌ Error!&nbsp;"
                self.request_render()
                QtCore.QTimer.singleShot(2500, lambda: self._reset_action(url_str))

    def _reset_action(self, action_id):
        if action_id in self.action_states:
            del self.action_states[action_id]
            self.request_render()

    # --- Session Management ---
    def refresh_session_list(self):
        while self.session_layout.count():
            item = self.session_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide(); w.setParent(None); w.deleteLater()
        for sess in self.core.get_all_sessions():
            is_active = (sess["id"] == self.core.session_id)
            widget = SessionItemWidget(sess["title"], sess["id"], is_active=is_active)
            widget.clicked.connect(self.on_session_clicked)
            widget.delete_requested.connect(self.delete_session)
            widget.rename_requested.connect(self.rename_session)
            self.session_layout.addWidget(widget)

    def delete_session(self, session_id):
        reply = QtWidgets.QMessageBox.question(
            self, 'Confirm Deletion', 'Are you sure you want to delete this session?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            if self.core.delete_session(session_id):
                self.refresh_session_list()
                self.request_render()

    def rename_session(self, session_id, new_title):
        self.core.rename_session(session_id, new_title)
        self.refresh_session_list()

    def on_new_chat(self):
        self.core.start_new_session()
        self.refresh_session_list()
        self.request_render()
        self.text_input.setFocus()

    def on_session_clicked(self, session_id):
        if session_id != self.core.session_id:
            if self.core.load_session(session_id):
                self.refresh_session_list()
                self.request_render()

    # --- Model Handling ---
    def load_models(self):
        self._loading_models = True
        self.model_combo.blockSignals(True)
        models = self.core.fetch_models()
        self.model_combo.addItems(models)
        self.model_combo.completer().setModel(self.model_combo.model())
        index = self.model_combo.findText(self.core.model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        self.current_model_display = self.model_combo.currentText()
        self.model_combo.blockSignals(False)
        self._loading_models = False

    def on_model_changed(self):
        if self._loading_models:
            return
        new_model = self.model_combo.currentText()
        if new_model and new_model != self.current_model_display:
            if self.core.session_id and len(self.core.get_chat_history()) > 0:
                self.core.append_to_history("system", f"--- Switched model to {new_model} ---")
            self.current_model_display = new_model
            self.core.set_model(new_model)
            self.request_render()

    def open_settings(self):
        old_key = self.core.api_key
        dialog = SettingsDialog(self.core, self)
        dialog.exec()
        if old_key != self.core.api_key:
            self.model_combo.clear()
            self.load_models()

    def eventFilter(self, obj, event):
        if obj == self.text_input and event.type() == QtCore.QEvent.KeyPress:
            if self.cmd_popup.isVisible():
                if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Tab):
                    item = self.cmd_popup.currentItem() or self.cmd_popup.item(0)
                    if item:
                        self.on_cmd_popup_selected(item)
                    return True
                elif event.key() == QtCore.Qt.Key_Down:
                    self.cmd_popup.setCurrentRow((self.cmd_popup.currentRow() + 1) % self.cmd_popup.count())
                    return True
                elif event.key() == QtCore.Qt.Key_Up:
                    row = self.cmd_popup.currentRow() - 1
                    self.cmd_popup.setCurrentRow(row if row >= 0 else self.cmd_popup.count() - 1)
                    return True
            if event.key() == QtCore.Qt.Key_Return and not event.modifiers() & QtCore.Qt.ShiftModifier:
                self.on_send_clicked()
                return True
        return super().eventFilter(obj, event)

    # --- Render Engine ---
    def update_context_ui(self):
        if not self.core.session_id:
            self.context_progress.setValue(0)
            self.context_progress.setFormat("Context: 0 / 50000 tokens")
            return
        current_tokens, limit, usage_pct = context_manager.calculate_session_usage(self.core.db_path, self.core.session_id)
        self.context_progress.setMaximum(limit)
        self.context_progress.setValue(current_tokens)
        self.context_progress.setFormat(f"Context: {current_tokens} / {limit} tokens")
        self.context_progress.setProperty("warning", usage_pct >= 75.0)
        self.context_progress.setProperty("danger", usage_pct >= 90.0)
        self.context_progress.style().unpolish(self.context_progress)
        self.context_progress.style().polish(self.context_progress)

    def request_render(self):
        self.needs_render = True
        if not self.render_timer.isActive():
            self.render_timer.start()

    def _on_render_tick(self):
        if self.needs_render:
            self.needs_render = False
            self._perform_render()
        else:
            self.render_timer.stop()

    def _perform_render(self):
        """Rebuild the chat display HTML from DB + streaming state."""
        self.code_blocks_store = {}
        html_parts = []
        for msg in self.core.get_chat_history():
            role = "User" if msg["role"] == "user" else ("System" if msg["role"] == "system" else "Agent")
            html_parts.append(build_bubble(role, msg["content"], self.code_blocks_store, self.action_states))
        if self.current_user_message is not None:
            html_parts.append(build_bubble("User", self.current_user_message, self.code_blocks_store, self.action_states))
        if self.current_agent_response is not None:
            s_role = "Thinking" if self.current_agent_response.startswith("Thinking") else "Agent"
            html_parts.append(build_bubble(s_role, self.current_agent_response, self.code_blocks_store, self.action_states))
        full_html = f"<body style='background-color: #333333; color: #dfdfdf; font-family: sans-serif; font-size: 14px;'>{''.join(html_parts)}</body>"
        vbar = self.chat_display.verticalScrollBar()
        saved_scroll = vbar.value()
        was_at_bottom = (saved_scroll >= vbar.maximum() - 20)
        self.chat_display.setUpdatesEnabled(False)
        self.chat_display.setHtml(full_html)
        if was_at_bottom:
            vbar.setValue(vbar.maximum())
        else:
            vbar.setValue(saved_scroll)
        self.chat_display.setUpdatesEnabled(True)
        self.update_context_ui()

    # --- Send / Streaming ---
    def on_send_clicked(self):
        user_text = self.text_input.toPlainText().strip()
        if not user_text:
            return
        if not self.core.api_key:
            self.core.append_to_history("system", "Please click the gear icon ⚙ at the top right to enter your OpenRouter API Key.")
            self.request_render()
            return
        self.text_input.clear()
        self.cmd_popup.hide()
        if user_text.lower() == "/compact":
            self.core.append_to_history("user", user_text)
            self.core.append_to_history("system", "Running manual compaction...")
            self._perform_render()
            QtWidgets.QApplication.processEvents()
            success, msg = context_manager.compact_session(self.core, self.core.session_id)
            self.core.append_to_history("system", msg)
            self.request_render()
            return

        self.send_btn.setEnabled(False)
        hou_context = self.context.get_selected_nodes_context()
        sys_prompt = self.context.generate_system_prompt()
        full_sys_context = sys_prompt + "\n\n" + hou_context
        self.current_user_message = user_text
        self.current_agent_response = "Thinking..."
        self.first_chunk_received = False
        self.request_render()
        self.thinking_dots = 0
        self.thinking_timer.start(400)
        self.worker = AgentWorker(self.core, user_text, full_sys_context, self)
        self.worker.chunk_received.connect(self.on_chunk_received)
        self.worker.finished_response.connect(self.on_response_finished)
        self.worker.start()

    def animate_thinking(self):
        if self.first_chunk_received:
            self.thinking_timer.stop()
            return
        self.thinking_dots = (self.thinking_dots + 1) % 4
        self.current_agent_response = "Thinking" + "." * self.thinking_dots
        self.request_render()

    def on_chunk_received(self, chunk):
        if not self.first_chunk_received:
            self.thinking_timer.stop()
            self.current_agent_response = ""
            self.first_chunk_received = True
        self.current_agent_response += chunk
        self.request_render()

    def on_response_finished(self):
        self.render_timer.stop()
        self.needs_render = False
        self.last_ai_response = self.current_agent_response
        self.current_user_message = None
        self.current_agent_response = None
        self.send_btn.setEnabled(True)
        self.refresh_session_list()
        self._perform_render()


def run_panel():
    return AIAgentUI()
