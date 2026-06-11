from PySide6 import QtWidgets, QtCore


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, core_ref, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.core = core_ref
        self.setWindowTitle("Settings")
        self.setFixedSize(450, 200)

        from styles import GLOBAL_STYLE

        self.setObjectName("SettingsDialog")
        self.setStyleSheet(GLOBAL_STYLE)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        link_label = QtWidgets.QLabel(
            'Get your API Key from <a href="https://openrouter.ai/keys">OpenRouter</a>'
        )
        link_label.setOpenExternalLinks(True)
        layout.addWidget(link_label)

        input_layout = QtWidgets.QHBoxLayout()
        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setPlaceholderText("sk-or-v1-...")
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_input.setText(self.core.api_key)

        self.toggle_btn = QtWidgets.QPushButton("👁")
        self.toggle_btn.setObjectName("ToggleBtn")
        self.toggle_btn.setToolTip("Show/Hide API Key")
        self.toggle_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_visibility)

        input_layout.addWidget(self.api_key_input)
        input_layout.addWidget(self.toggle_btn)

        layout.addWidget(QtWidgets.QLabel("OpenRouter API Key:"))
        layout.addLayout(input_layout)

        btn_layout = QtWidgets.QHBoxLayout()

        self.delete_btn = QtWidgets.QPushButton("Delete Key")
        self.delete_btn.setObjectName("DeleteBtn")
        self.delete_btn.setToolTip("Permanently delete the saved API key")
        self.delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self.on_delete_clicked)

        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()

        self.save_btn = QtWidgets.QPushButton("Save && Close")
        self.save_btn.setObjectName("SaveBtn")
        self.save_btn.setToolTip("Save settings and close window")
        self.save_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.on_save_clicked)

        btn_layout.addWidget(self.save_btn)
        layout.addStretch()
        layout.addLayout(btn_layout)

    def toggle_visibility(self):
        if self.api_key_input.echoMode() == QtWidgets.QLineEdit.Password:
            self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.toggle_btn.setText("🙈")
        else:
            self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
            self.toggle_btn.setText("👁")

    def on_delete_clicked(self):
        reply = QtWidgets.QMessageBox.warning(
            self,
            "Delete API Key",
            "Are you sure you want to delete your API key and clear the configuration file?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.core.delete_config()
            self.api_key_input.clear()
            self.accept()

    def on_save_clicked(self):
        self.core.set_api_key(self.api_key_input.text().strip())
        self.accept()
