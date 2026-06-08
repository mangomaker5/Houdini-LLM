from PySide6 import QtWidgets, QtCore, QtGui
from settings_dialog import SettingsDialog


class UIActionsMixin:
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
            block_id = url_str[len("copy_code:") :].strip("/")
            if block_id in self.code_blocks_store:
                try:
                    import hou

                    hou.ui.copyTextToClipboard(self.code_blocks_store[block_id])
                except Exception:
                    QtWidgets.QApplication.clipboard().setText(
                        self.code_blocks_store[block_id]
                    )
                self.action_states[url_str] = "&nbsp;✅ Copied!&nbsp;"
                self.request_render()
                QtCore.QTimer.singleShot(2000, lambda: self._reset_action(url_str))
        elif url_str.startswith("run_code:"):
            block_id = url_str[len("run_code:") :].strip("/")
            if block_id in self.code_blocks_store:
                success, msg = self.context.execute_code_block(
                    self.code_blocks_store[block_id]
                )
                self.action_states[url_str] = (
                    "&nbsp;✅ Success!&nbsp;" if success else "&nbsp;❌ Error!&nbsp;"
                )
                self.request_render()
                QtCore.QTimer.singleShot(2500, lambda: self._reset_action(url_str))

    def _reset_action(self, action_id):
        if action_id in self.action_states:
            del self.action_states[action_id]
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
