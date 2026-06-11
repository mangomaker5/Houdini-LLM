from PySide6 import QtGui, QtWidgets, QtCore
from settings_dialog import SettingsDialog


class UIActionsMixin:
    # --- Autocomplete ---
    def on_text_changed(self):
        text = self.text_input.toPlainText().strip()
        # Only show popup when user is typing a bare slash command (no space yet).
        # e.g. "/" or "/arn" → show popup.  "/arnold create light" → hide.
        show = (
            text.startswith("/")
            and " " not in text
            and text != "/compact"
            and text != "/usage"
        )
        self.cmd_popup.setVisible(show)

    def on_cmd_popup_selected(self, item):
        cmd = item.text().split(" ")[0]
        # Add trailing space so the user can immediately type their prompt
        if cmd != "/compact":
            cmd += " "
        self.text_input.setText(cmd)
        cursor = self.text_input.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.text_input.setTextCursor(cursor)
        self.cmd_popup.hide()

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
                self.core.append_to_history(
                    "system", f"--- Switched model to {new_model} ---"
                )
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

            current_state = self.action_states.get(link, "")
            if "Saving..." in current_state or "Saved!" in current_state:
                return

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
        from memory_db import get_all_learned_skills, delete_learned_skill

        from styles import GLOBAL_STYLE

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Manage Memory")
        dialog.setStyleSheet(GLOBAL_STYLE)
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
            "background-color: #1e1e1e; border: 1px solid #444444; color: #cccccc; font-family: 'Consolas', monospace;"
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
        delete_btn.setStyleSheet(
            "background-color: #ef4444; color: white; padding: 8px; border-radius: 4px;"
        )
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setStyleSheet(
            "background-color: #444444; color: white; padding: 8px; border-radius: 4px;"
        )
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

        # After dialog closes, clear save button states so they re-check DB
        stale_keys = [k for k in self.action_states if k.startswith("save_code:")]
        for k in stale_keys:
            del self.action_states[k]
        self.request_render()
