from PySide6 import QtCore
import context_manager
from chat_formatter import build_bubble


class UIRenderMixin:
    # --- Render Engine ---
    def update_context_ui(self):
        if not self.core.session_id:
            self.context_progress.setValue(0)
            self.context_progress.setFormat("Context: 0 / 50000 tokens")
            return
        current_tokens, limit, usage_pct = context_manager.calculate_session_usage(
            self.core.db_path, self.core.session_id
        )
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
        for i, msg in enumerate(self.core.get_chat_history()):
            if msg["role"] == "user":
                role = "User"
            elif msg["role"] == "system":
                role = "System"
            elif msg["role"] == "assistant_mcp":
                role = "Agent (MCP)"
            else:
                role = "Agent"

            # Elegantly hide the header if the previous message was from the same role
            show_header = True
            if i > 0 and self.core.get_chat_history()[i - 1]["role"] == msg["role"]:
                show_header = False

            html_parts.append(
                build_bubble(
                    role,
                    msg["content"],
                    show_header=show_header,
                )
            )

        if self.current_agent_response is not None:
            is_thinking = self.current_agent_response.startswith(
                "Thinking"
            ) or self.current_agent_response.startswith("⚡ Agent Mode Auto Working")
            s_role = (
                "Thinking"
                if is_thinking
                else (
                    "Agent (MCP)"
                    if hasattr(self, "agent_mode_toggle")
                    and self.agent_mode_toggle.isChecked()
                    else "Agent"
                )
            )
            html_parts.append(
                build_bubble(
                    s_role,
                    self.current_agent_response,
                )
            )
        full_html = f"<body style='background-color: #333333; color: #dfdfdf; font-family: sans-serif; font-size: 14px;'>{''.join(html_parts)}</body>"
        vbar = self.chat_display.verticalScrollBar()
        saved_scroll = vbar.value()

        # Determine if we are currently at the bottom (with a little padding)
        was_at_bottom = saved_scroll >= vbar.maximum() - 25

        self.chat_display.setUpdatesEnabled(False)
        self.chat_display.setHtml(full_html)

        # Force document layout calculation to update vbar.maximum() immediately
        self.chat_display.document().documentLayout().documentSize()

        if was_at_bottom:
            vbar.setValue(vbar.maximum())
        else:
            vbar.setValue(saved_scroll)

        self.chat_display.setUpdatesEnabled(True)

        # Ensure scroll stays at the bottom after event loop processes painting
        if was_at_bottom:
            QtCore.QTimer.singleShot(0, lambda: vbar.setValue(vbar.maximum()))

        self.update_context_ui()
