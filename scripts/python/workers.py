from PySide6 import QtCore
import context_manager


class AgentWorker(QtCore.QThread):
    chunk_received = QtCore.Signal(str)
    finished_response = QtCore.Signal()

    def __init__(
        self, core, user_message, system_context, agent_mode=False, parent=None
    ):
        super().__init__(parent)
        self.core = core
        self.user_message = user_message
        self.system_context = system_context
        self.agent_mode = agent_mode
        self.is_cancelled = False

    def stop(self):
        self.is_cancelled = True

    def check_cancelled(self):
        return self.is_cancelled

    def run(self):
        current_tokens, limit, usage_pct = context_manager.calculate_session_usage(
            self.core.db_path, self.core.session_id
        )
        if usage_pct > 80.0:
            self.chunk_received.emit("\n*System: Auto-compacting history...*\n")
            success, msg = context_manager.compact_session(
                self.core, self.core.session_id
            )
            self.chunk_received.emit(f"*{msg}*\n\n")

        for chunk in self.core.generate_response_stream(
            self.user_message,
            self.system_context,
            self.agent_mode,
            self.check_cancelled,
        ):
            if self.is_cancelled:
                break
            self.chunk_received.emit(chunk)
        self.finished_response.emit()
