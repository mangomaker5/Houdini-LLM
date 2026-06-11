from PySide6 import QtWidgets, QtCore, QtGui


class ElidedLabel(QtWidgets.QLabel):
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        metrics = QtGui.QFontMetrics(self.font())
        elided = metrics.elidedText(self.text(), QtCore.Qt.ElideRight, self.width())
        painter.setPen(self.palette().color(QtGui.QPalette.WindowText))
        painter.drawText(self.rect(), self.alignment(), elided)

    def minimumSizeHint(self):
        return QtCore.QSize(30, self.fontMetrics().height())


class SessionItemWidget(QtWidgets.QWidget):
    clicked = QtCore.Signal(str)
    delete_requested = QtCore.Signal(str)
    rename_requested = QtCore.Signal(str, str)

    def __init__(self, title, session_id, is_active=False, parent=None):
        super().__init__(parent)
        self.session_id = session_id

        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setObjectName("SessionItemWidget")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedHeight(40)

        if is_active:
            self.setProperty("active", True)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 0)
        layout.setSpacing(5)

        self.title_label = ElidedLabel(title)
        self.title_label.setObjectName("SessionTitleLabel")
        self.title_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_label.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )

        self.edit_btn = QtWidgets.QPushButton("Rename")
        self.edit_btn.setObjectName("SessionEditBtn")
        self.edit_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.edit_btn.setToolTip("Rename Session")
        self.edit_btn.clicked.connect(self.on_edit_clicked)

        self.delete_btn = QtWidgets.QPushButton("Delete")
        self.delete_btn.setObjectName("SessionDeleteBtn")
        self.delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.delete_btn.setToolTip("Delete Session")
        self.delete_btn.clicked.connect(self.on_delete_clicked)

        layout.addWidget(self.title_label, stretch=1)
        layout.addWidget(self.edit_btn)
        layout.addWidget(self.delete_btn)

    def on_edit_clicked(self, *args):
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename Session",
            "New Name:",
            QtWidgets.QLineEdit.Normal,
            self.title_label.text(),
        )
        if ok and text.strip():
            self.title_label.setText(text.strip())
            self.rename_requested.emit(self.session_id, text.strip())

    def on_delete_clicked(self, *args):
        self.delete_requested.emit(self.session_id)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self.session_id)
        super().mousePressEvent(event)


class ChatTextBrowser(QtWidgets.QTextBrowser):
    custom_link_clicked = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            anchor = self.anchorAt(event.pos())
            if anchor:
                if (
                    anchor.startswith("copy_code:")
                    or anchor.startswith("run_code:")
                    or anchor.startswith("save_code:")
                ):
                    self.custom_link_clicked.emit(anchor)
                    return
                elif anchor.startswith("http"):
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))
                    return
        super().mouseReleaseEvent(event)
