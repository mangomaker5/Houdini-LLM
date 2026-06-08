from PySide6 import QtWidgets, QtCore

from core import AIAgentCore
from houdini_context import HoudiniContext
from styles import GLOBAL_STYLE
import context_manager

from workers import AgentWorker

from ui_builder import UIBuilderMixin
from ui_session import UISessionMixin
from ui_render import UIRenderMixin
from ui_actions import UIActionsMixin
from personas import get_persona_prompt


class AIAgentUI(
    QtWidgets.QWidget, UIBuilderMixin, UISessionMixin, UIRenderMixin, UIActionsMixin
):
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
        self.persona_combo.currentIndexChanged.connect(self.on_persona_changed)
        self.approve_btn.clicked.connect(self.on_approve_code)
        self.reject_btn.clicked.connect(self.on_reject_code)
        self.save_code_btn.clicked.connect(self.on_save_pending_code)
        self.manage_memory_btn.clicked.connect(self.on_manage_memory)
        self.load_models()
        self.refresh_session_list()
        self.request_render()

    def on_persona_changed(self, index):
        if self.core.session_id and len(self.core.get_chat_history()) > 0:
            persona_name = self.persona_combo.currentText()
            warning_msg = f"Switched persona to: {persona_name}"
            # Send as a system message to show as warning
            self.core.append_to_history("system", warning_msg)
            self.refresh_session_list()
            self.request_render()

    def eventFilter(self, obj, event):
        if obj == self.text_input and event.type() == QtCore.QEvent.KeyPress:
            if self.cmd_popup.isVisible():
                if event.key() in (
                    QtCore.Qt.Key_Return,
                    QtCore.Qt.Key_Enter,
                    QtCore.Qt.Key_Tab,
                ):
                    item = self.cmd_popup.currentItem() or self.cmd_popup.item(0)
                    if item:
                        self.on_cmd_popup_selected(item)
                    return True
                elif event.key() == QtCore.Qt.Key_Down:
                    self.cmd_popup.setCurrentRow(
                        (self.cmd_popup.currentRow() + 1) % self.cmd_popup.count()
                    )
                    return True
                elif event.key() == QtCore.Qt.Key_Up:
                    row = self.cmd_popup.currentRow() - 1
                    self.cmd_popup.setCurrentRow(
                        row if row >= 0 else self.cmd_popup.count() - 1
                    )
                    return True
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and not (
                event.modifiers() & QtCore.Qt.ShiftModifier
            ):
                self.on_send_clicked()
                return True
        return super().eventFilter(obj, event)

    # --- Send / Streaming ---
    def on_send_clicked(self):
        # Kill Switch Logic
        if (
            self.send_btn.text() == "◼"
            and hasattr(self, "worker")
            and self.worker.isRunning()
        ):
            self.worker.stop()
            self.send_btn.setText("↑")
            self.send_btn.setEnabled(True)
            self.new_chat_btn.setEnabled(True)
            self.session_scroll.setEnabled(True)
            self.text_input.setEnabled(True)
            self.text_input.setFocus()

            # Save the stopped message directly to DB to ensure it renders!
            stop_msg = "\n\n*[Stopped by User]*"
            self.core.append_to_history("assistant", stop_msg)

            self.current_agent_response = ""
            self.request_render()
            return

        user_text = self.text_input.toPlainText().strip()
        if not user_text:
            return
        if not self.core.api_key:
            self.core.append_to_history(
                "system",
                "Please click the gear icon ⚙ at the top right to enter your OpenRouter API Key.",
            )
            self.request_render()
            return
        self.text_input.clear()
        self.cmd_popup.hide()
        if user_text.lower() == "/compact":
            self.core.append_to_history("user", user_text)
            self.core.append_to_history("system", "Running manual compaction...")
            self._perform_render()
            QtWidgets.QApplication.processEvents()
            success, msg = context_manager.compact_session(
                self.core, self.core.session_id
            )
            self.core.append_to_history("system", msg)
            self.request_render()
            return

        # Start Generation
        self.send_btn.setText("◼")
        self.new_chat_btn.setEnabled(False)
        self.session_scroll.setEnabled(False)
        self.text_input.setEnabled(False)

        # Save user message immediately to the DB to prevent disappearance or double rendering
        if not self.core.session_id:
            self.core.start_new_session()
        self.core.append_to_history("user", user_text)
        self.refresh_session_list()

        hou_context = self.context.get_selected_nodes_context()
        sys_prompt = get_persona_prompt(self.persona_combo.currentText())
        full_sys_context = sys_prompt + "\n\n" + hou_context

        agent_mode_active = self.agent_mode_toggle.isChecked()
        self.thinking_base_text = (
            "⚡ Agent Mode Auto Working" if agent_mode_active else "Thinking"
        )
        self.current_agent_response = self.thinking_base_text + "..."
        self.first_chunk_received = False
        self.request_render()
        self.thinking_dots = 0
        self.thinking_timer.start(400)

        agent_mode_active = self.agent_mode_toggle.isChecked()
        self.worker = AgentWorker(
            self.core, user_text, full_sys_context, agent_mode_active, self
        )
        self.worker.chunk_received.connect(self.on_chunk_received)
        self.worker.finished_response.connect(self.on_response_finished)
        self.worker.code_proposed.connect(self.on_code_proposed)
        self.worker.start()

    def animate_thinking(self):
        if self.first_chunk_received:
            self.thinking_timer.stop()
            return
        self.thinking_dots = (self.thinking_dots + 1) % 4
        base_text = getattr(self, "thinking_base_text", "Thinking")
        self.current_agent_response = base_text + "." * self.thinking_dots
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
        self.current_agent_response = None
        self.send_btn.setText("↑")
        self.send_btn.setEnabled(True)
        self.new_chat_btn.setEnabled(True)
        self.session_scroll.setEnabled(True)
        self.text_input.setEnabled(True)
        self.text_input.setFocus()
        self.refresh_session_list()
        self._perform_render()

    def on_code_proposed(self, code):
        if code:
            self.review_code.setPlainText(code)
            self.review_panel.show()
            self.pending_code = code

    def on_approve_code(self):
        if not hasattr(self, "pending_code") or not self.pending_code:
            return
        self.review_panel.hide()
        code = self.pending_code
        self.pending_code = None

        import hou

        print("\n--- Agent Execution Started ---")
        with hou.undos.group("Agent Execution"):
            local_dict = {"hou": hou}
            exec(code, local_dict)

        print("--- Agent Execution Success ---\n")
        self.core.append_to_history(
            "user",
            "I approved and ran the proposed code. It executed successfully.",
        )

        self.refresh_session_list()
        self.request_render()

    def on_save_pending_code(self):
        if not hasattr(self, "pending_code") or not self.pending_code:
            return
        from workers import ReflectionWorker

        code = self.pending_code
        self.save_code_btn.setText("⏳ Saving...")
        self.save_code_btn.setEnabled(False)
        worker = ReflectionWorker(self.core, code, "save_btn", self)
        worker.finished_reflection.connect(self.on_reflection_finished)
        if not hasattr(self, "reflection_workers"):
            self.reflection_workers = []
        self.reflection_workers.append(worker)
        worker.start()

    def on_reflection_finished(self, url_str, success, message):
        worker = self.sender()
        if hasattr(self, "reflection_workers") and worker in self.reflection_workers:
            self.reflection_workers.remove(worker)
        if success:
            self.save_code_btn.setText("✅ Saved!")
        else:
            self.save_code_btn.setText(f"❌ Failed: {message}")
        QtCore.QTimer.singleShot(3000, self._reset_save_btn)

    def _reset_save_btn(self):
        self.save_code_btn.setText("🌟 Save to Memory")
        self.save_code_btn.setEnabled(True)

    def on_reject_code(self):
        self.review_panel.hide()
        self.pending_code = None
        self.core.append_to_history(
            "user",
            "I rejected the proposed code. Please revise it or ask for clarification.",
        )
        self.refresh_session_list()
        self.request_render()

    def on_manage_memory(self):
        from database import get_all_learned_skills, delete_learned_skill

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Manage Memory")
        dialog.resize(600, 400)
        layout = QtWidgets.QVBoxLayout(dialog)

        list_widget = QtWidgets.QListWidget()
        skills = get_all_learned_skills(self.core.db_path)
        for skill in skills:
            item = QtWidgets.QListWidgetItem(f"[{skill['id']}] {skill['description']}")
            item.setData(QtCore.Qt.UserRole, skill["id"])
            list_widget.addItem(item)

        layout.addWidget(list_widget)

        btn_layout = QtWidgets.QHBoxLayout()
        delete_btn = QtWidgets.QPushButton("Delete Selected")
        close_btn = QtWidgets.QPushButton("Close")
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        def on_delete():
            item = list_widget.currentItem()
            if item:
                skill_id = item.data(QtCore.Qt.UserRole)
                delete_learned_skill(self.core.db_path, skill_id)
                list_widget.takeItem(list_widget.row(item))

        delete_btn.clicked.connect(on_delete)
        close_btn.clicked.connect(dialog.accept)

        dialog.exec()


def run_panel():
    return AIAgentUI()
