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
        import datetime

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Manage Memory")
        dialog.setStyleSheet(GLOBAL_STYLE)
        dialog.resize(900, 600)
        layout = QtWidgets.QVBoxLayout(dialog)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # --- Left Panel (Table & Search) ---
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        search_box = QtWidgets.QLineEdit()
        search_box.setPlaceholderText("🔍 Search Title or Code...")
        left_layout.addWidget(search_box)

        table = QtWidgets.QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["ID", "Description", "Size", "Date Added"])
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeToContents
        )
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        left_layout.addWidget(table)

        stats_label = QtWidgets.QLabel()
        left_layout.addWidget(stats_label)

        # --- Right Panel (Code Preview) ---
        code_preview = QtWidgets.QTextBrowser()
        code_preview.setObjectName("CodePreview")

        class NumericTableWidgetItem(QtWidgets.QTableWidgetItem):
            def __lt__(self, other):
                my_val = self.data(QtCore.Qt.UserRole)
                other_val = other.data(QtCore.Qt.UserRole)
                if my_val is not None and other_val is not None:
                    return float(my_val) < float(other_val)
                return super().__lt__(other)

        skills = get_all_learned_skills(self.core.db_path)
        skills_dict = {}

        def populate_table():
            table.setSortingEnabled(False)
            table.setRowCount(0)
            total_size = 0
            visible_count = 0

            search_text = search_box.text().lower()

            for skill in skills:
                code_text = skill.get("code", "")
                desc_text = skill.get("description", "")

                # Filtering
                if search_text:
                    if (
                        search_text not in desc_text.lower()
                        and search_text not in code_text.lower()
                    ):
                        continue

                skills_dict[skill["id"]] = code_text
                row = table.rowCount()
                table.insertRow(row)

                # ID
                id_item = QtWidgets.QTableWidgetItem()
                id_item.setData(QtCore.Qt.DisplayRole, skill["id"])

                # Description
                desc_item = QtWidgets.QTableWidgetItem(desc_text)

                # Size
                size_bytes = len(code_text.encode("utf-8"))
                total_size += size_bytes
                size_kb = size_bytes / 1024.0
                size_str = f"{size_kb:.1f} KB" if size_kb >= 1.0 else f"{size_bytes} B"
                size_item = NumericTableWidgetItem(size_str)
                size_item.setData(QtCore.Qt.UserRole, size_bytes)

                # Date Added
                created_at = skill.get("created_at", 0)
                if created_at:
                    dt = datetime.datetime.fromtimestamp(created_at)
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    date_str = "Unknown"
                date_item = QtWidgets.QTableWidgetItem(date_str)

                table.setItem(row, 0, id_item)
                table.setItem(row, 1, desc_item)
                table.setItem(row, 2, size_item)
                table.setItem(row, 3, date_item)
                visible_count += 1

            total_kb = total_size / 1024.0
            stats_label.setText(
                f"<b>Total Skills:</b> {visible_count} &nbsp;|&nbsp; <b>Total Size:</b> {total_kb:.1f} KB"
            )
            table.setSortingEnabled(True)

        populate_table()
        search_box.textChanged.connect(populate_table)

        def on_selection_changed():
            selected = table.selectedItems()
            if selected:
                row = selected[0].row()
                skill_id = table.item(row, 0).data(QtCore.Qt.DisplayRole)
                code_preview.setPlainText(skills_dict.get(skill_id, ""))
            else:
                code_preview.clear()

        table.itemSelectionChanged.connect(on_selection_changed)

        splitter.addWidget(left_panel)
        splitter.addWidget(code_preview)
        splitter.setSizes([500, 400])

        layout.addWidget(splitter)

        # --- Bottom Bar ---
        btn_layout = QtWidgets.QHBoxLayout()

        warning_label = QtWidgets.QLabel(
            "⚠️ WARNING: Deleting a skill is permanent. It cannot be recovered."
        )
        warning_label.setObjectName("WarningLabel")
        btn_layout.addWidget(warning_label)

        btn_layout.addStretch()

        delete_btn = QtWidgets.QPushButton("Delete Selected")
        delete_btn.setObjectName("DangerBtn")
        delete_btn.setToolTip("Permanently delete the selected skills")
        delete_btn.setCursor(QtCore.Qt.PointingHandCursor)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setObjectName("CloseBtn")
        close_btn.setToolTip("Close the Manage Memory window")
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)

        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        def on_delete():
            selected_ranges = table.selectedRanges()
            if not selected_ranges:
                return

            reply = QtWidgets.QMessageBox.warning(
                dialog,
                "Confirm Deletion",
                "Are you sure you want to permanently delete the selected skill(s)?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

            rows_to_delete = []
            for r in selected_ranges:
                for row in range(r.topRow(), r.bottomRow() + 1):
                    rows_to_delete.append(row)

            rows_to_delete.sort(reverse=True)

            for row in rows_to_delete:
                skill_id = table.item(row, 0).data(QtCore.Qt.DisplayRole)
                delete_learned_skill(self.core.db_path, skill_id)
                # Remove from local list so it stays removed during filtering
                for i, s in enumerate(skills):
                    if s["id"] == skill_id:
                        skills.pop(i)
                        break

            populate_table()

        delete_btn.clicked.connect(on_delete)
        close_btn.clicked.connect(dialog.accept)

        dialog.exec()

        # After dialog closes, clear save button states so they re-check DB
        stale_keys = [k for k in self.action_states if k.startswith("save_code:")]
        for k in stale_keys:
            del self.action_states[k]
        self.request_render()
