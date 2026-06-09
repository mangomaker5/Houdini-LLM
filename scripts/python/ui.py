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
        self.retry_btn.clicked.connect(self.on_retry_execution)
        self.chat_display.custom_link_clicked.connect(self.on_custom_link_clicked)
        self.manage_memory_btn.clicked.connect(self.on_manage_memory)
        self.load_models()
        self.refresh_session_list()
        self.request_render()
        self.run_startup_diagnostics()

    def run_startup_diagnostics(self):
        import importlib.util

        print("\n--- [Houdini-LLM] Startup Diagnostics ---")

        if importlib.util.find_spec("sqlite3") is not None:
            print("  [OK] sqlite3 loaded successfully.")
        else:
            print("  [ERROR] sqlite3 not found! Please run install_dependencies.bat")

        if importlib.util.find_spec("sqlite_vec") is not None:
            print("  [OK] sqlite-vec loaded successfully.")
        else:
            print(
                "  [ERROR] sqlite-vec not found! Vector memory will not work. Please run install_dependencies.bat"
            )

        if importlib.util.find_spec("pygments") is not None:
            print("  [OK] pygments loaded successfully.")
        else:
            print(
                "  [ERROR] pygments not found! Syntax highlighting will not work. Please run install_dependencies.bat"
            )
        print("------------------------------------------\n")

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

            self.is_agent_thinking = False
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

        agent_mode_active = True
        self.thinking_base_text = "✨ Thinking"
        self.thinking_color = "#f1c40f"
        self.is_agent_thinking = True
        self.current_agent_response = ""
        self.first_chunk_received = False
        self.request_render()
        self.thinking_dots = 0
        self.thinking_timer.start(400)

        self.worker = AgentWorker(
            self.core, user_text, full_sys_context, agent_mode_active, self
        )
        self.worker.status_update.connect(self.on_agent_status_update)
        self.worker.chunk_received.connect(self.on_chunk_received)
        self.worker.finished_response.connect(self.on_response_finished)
        self.worker.code_proposed.connect(self.on_code_proposed)
        self.worker.start()

    def animate_thinking(self):
        if getattr(self, "is_agent_thinking", False):
            self.thinking_dots = (self.thinking_dots + 1) % 4
            self.request_render()

    def on_agent_status_update(self, msg, color):
        self.is_agent_thinking = True
        self.thinking_base_text = msg
        self.thinking_color = color
        self.request_render()

    def on_chunk_received(self, chunk):
        self.is_agent_thinking = False
        self.current_agent_response += chunk
        self.request_render()

    def on_response_finished(self):
        self.is_agent_thinking = False
        self.thinking_timer.stop()
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
            self.code_executed = False

            self.retry_btn.hide()
            self.approve_btn.show()
            self.approve_btn.setEnabled(True)
            self.approve_btn.setText("✅ Approve & Run")

            self.reject_btn.setText("❌ Reject")
            self.reject_btn.setStyleSheet(
                "QPushButton { background-color: #ff4a4a; color: white; font-weight: bold; padding: 5px; border-radius: 4px; }"
            )
            self.reject_btn.show()

    def on_approve_code(self):
        if not hasattr(self, "pending_code") or not self.pending_code:
            return

        code = self.pending_code
        self.code_executed = True

        import hou
        import traceback

        print("\n--- Agent Execution Started ---")
        try:
            with hou.undos.group("Agent Execution"):
                local_dict = {"hou": hou}
                exec(code, local_dict)

            print("--- Agent Execution Success ---\n")
            self.core.append_to_history(
                "user",
                "I approved and ran the proposed code. It executed successfully.",
            )

            # Hide panel completely on success! (User can rely on inline buttons now)
            self.review_panel.hide()

        except Exception as e:
            err_trace = traceback.format_exc()
            print(f"--- Agent Execution Failed ---\n{err_trace}")
            import json

            error_feedback = {
                "status": "failed",
                "error_type": type(e).__name__,
                "message": str(e),
                "traceback": err_trace,
                "instruction": "Please analyze the error and propose fixed code.",
            }
            json_str = json.dumps(error_feedback, indent=2)
            self.last_error_message = f"```json\n{json_str}\n```"
            self.core.append_to_history("user", self.last_error_message)

            self.approve_btn.hide()
            self.retry_btn.show()

            self.reject_btn.setText("Close")
            self.reject_btn.setStyleSheet(
                "QPushButton { background-color: #444444; color: white; font-weight: bold; padding: 5px; border-radius: 4px; }"
            )

        self.refresh_session_list()
        self.request_render()

    def on_retry_execution(self):
        self.review_panel.hide()
        self.text_input.setPlainText(
            getattr(self, "last_error_message", "Retry please.")
        )
        self.on_send_clicked()

    def on_custom_link_clicked(self, link):
        action, block_id = link.split(":", 1)
        code = self.code_blocks_store.get(block_id, "")
        if not code:
            return

        if action == "copy_code":
            QtWidgets.QApplication.clipboard().setText(code)
            self.action_states[link] = "&nbsp;✅ Copied!&nbsp;"
            self.request_render()
            QtCore.QTimer.singleShot(
                2000, lambda: self.reset_action_state(link, "&nbsp;📋 Copy Code&nbsp;")
            )

        elif action == "run_code":
            import hou

            try:
                with hou.undos.group("Agent Execution (Inline)"):
                    local_dict = {"hou": hou}
                    exec(code, local_dict)
                self.action_states[link] = "&nbsp;✅ Success!&nbsp;"
            except Exception as e:
                self.action_states[link] = "&nbsp;❌ Failed!&nbsp;"
                print(f"Code execution error:\n{e}")
            self.request_render()
            QtCore.QTimer.singleShot(
                3000, lambda: self.reset_action_state(link, "&nbsp;▶ Run Code&nbsp;")
            )

        elif action == "save_code":
            from workers import ReflectionWorker

            self.action_states[link] = "&nbsp;⏳ Saving...&nbsp;"
            self.request_render()

            worker = ReflectionWorker(self.core, code, link, self)
            worker.finished_reflection.connect(self.on_reflection_finished)
            if not hasattr(self, "reflection_workers"):
                self.reflection_workers = []
            self.reflection_workers.append(worker)
            worker.start()

    def reset_action_state(self, link, default_text):
        if link in self.action_states:
            self.action_states[link] = default_text
            self.request_render()

    def on_reflection_finished(self, url_str, success, message):
        worker = self.sender()
        if hasattr(self, "reflection_workers") and worker in self.reflection_workers:
            self.reflection_workers.remove(worker)

        if url_str.startswith("save_code:"):
            if success:
                self.action_states[url_str] = "&nbsp;✅ Saved!&nbsp;"
                self.request_render()
                # Do NOT reset if successful, so the user knows it's saved.
            else:
                self.action_states[url_str] = f"&nbsp;❌ Failed: {message}&nbsp;"
                self.request_render()
                QtCore.QTimer.singleShot(
                    3000,
                    lambda: self.reset_action_state(
                        url_str, "&nbsp;🌟 Save to Memory&nbsp;"
                    ),
                )

    def on_reject_code(self):
        self.review_panel.hide()
        self.pending_code = None

        if not getattr(self, "code_executed", False):
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
        dialog.resize(800, 500)
        layout = QtWidgets.QVBoxLayout(dialog)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        list_widget = QtWidgets.QListWidget()
        skills = get_all_learned_skills(self.core.db_path)

        # We need a dictionary to quickly look up code by id
        skills_dict = {}
        for skill in skills:
            skills_dict[skill["id"]] = skill.get("code", "")
            item = QtWidgets.QListWidgetItem(f"[{skill['id']}] {skill['description']}")
            item.setData(QtCore.Qt.UserRole, skill["id"])
            list_widget.addItem(item)

        code_preview = QtWidgets.QTextBrowser()
        code_preview.setStyleSheet(
            "background-color: #1e1e1e; color: #cccccc; font-family: 'Consolas', monospace;"
        )

        def on_item_changed(current, previous):
            if current:
                skill_id = current.data(QtCore.Qt.UserRole)
                code_preview.setPlainText(skills_dict.get(skill_id, ""))
            else:
                code_preview.clear()

        list_widget.currentItemChanged.connect(on_item_changed)

        splitter.addWidget(list_widget)
        splitter.addWidget(code_preview)
        splitter.setSizes([300, 500])

        layout.addWidget(splitter)

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
