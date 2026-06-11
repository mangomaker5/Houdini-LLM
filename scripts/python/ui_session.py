from PySide6 import QtWidgets
from components import SessionItemWidget


class UISessionMixin:
    # --- Session Management ---
    def refresh_session_list(self):
        while self.session_layout.count():
            item = self.session_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for sess in self.core.get_all_sessions():
            is_active = sess["id"] == self.core.session_id
            widget = SessionItemWidget(sess["title"], sess["id"], is_active=is_active)
            widget.clicked.connect(self.on_session_clicked)
            widget.delete_requested.connect(self.delete_session)
            widget.rename_requested.connect(self.rename_session)
            self.session_layout.addWidget(widget)

    def delete_session(self, session_id):
        if hasattr(self, "worker") and self.worker.isRunning():
            QtWidgets.QMessageBox.warning(
                self,
                "Warning",
                "Please stop the active agent before deleting a session.",
            )
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deletion",
            "Are you sure you want to delete this session?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            if self.core.delete_session(session_id):
                self.refresh_session_list()
                self.request_render()

    def rename_session(self, session_id, new_title):
        if hasattr(self, "worker") and self.worker.isRunning():
            return
        self.core.rename_session(session_id, new_title)
        self.refresh_session_list()

    def on_new_chat(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            return
        self.core.start_new_session()
        self.refresh_session_list()
        self.request_render()
        self.text_input.setFocus()

    def on_session_clicked(self, session_id):
        if hasattr(self, "worker") and self.worker.isRunning():
            return
        if session_id != self.core.session_id:
            if self.core.load_session(session_id):
                self.refresh_session_list()
                self.request_render()
