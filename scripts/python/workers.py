from PySide6 import QtCore
import context_manager
import urllib.error


class AgentWorker(QtCore.QThread):
    chunk_received = QtCore.Signal(str)
    finished_response = QtCore.Signal()
    code_proposed = QtCore.Signal(str)
    status_update = QtCore.Signal(str, str)

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
            on_code_proposed=self.code_proposed.emit,
            on_status_update=self.status_update.emit,
        ):
            if self.is_cancelled:
                break
            self.chunk_received.emit(chunk)
        self.finished_response.emit()


class ReflectionWorker(QtCore.QThread):
    finished_reflection = QtCore.Signal(str, bool, str)

    def __init__(self, core, code_block, url_str, parent=None):
        super().__init__(parent)
        self.core = core
        self.code_block = code_block
        self.url_str = url_str

    def run(self):
        try:
            # 1. Summarize the code to get a description
            prompt = f"Analyze the following Houdini Python code and provide a single concise sentence describing exactly what it does. Do not include any other text.\n\nCode:\n{self.code_block}"
            description = self.core.generate_response_sync(
                prompt, system_context="You are a concise summarizer."
            )

            # 2. Generate Embedding
            embedding = self.core.generate_embedding(description)
            if not embedding:
                self.finished_reflection.emit(
                    self.url_str, False, "Failed to generate embedding"
                )
                return

            # 3. Save to database
            from memory_db import (
                save_learned_skill,
                check_skill_duplicate,
                update_learned_skill,
            )

            duplicate = check_skill_duplicate(
                self.core.db_path, embedding, threshold=0.15
            )
            if duplicate:
                success = update_learned_skill(
                    self.core.db_path,
                    duplicate["id"],
                    description,
                    self.code_block,
                    embedding,
                )
            else:
                success = save_learned_skill(
                    self.core.db_path, description, self.code_block, embedding
                )

            if not success:
                self.finished_reflection.emit(
                    self.url_str, False, "Vector DB extension not loaded"
                )
                return

            self.finished_reflection.emit(self.url_str, True, "Saved successfully")
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
                print(f"Network Error in Reflection: HTTP {e.code}: {error_body}")
                self.finished_reflection.emit(
                    self.url_str, False, f"HTTP {e.code}: {error_body}"
                )
            except Exception:
                print(f"Network Error in Reflection: {str(e)}")
                self.finished_reflection.emit(self.url_str, False, str(e))
        except Exception as e:
            print(f"Error in Reflection: {str(e)}")
            self.finished_reflection.emit(self.url_str, False, str(e))


class CompactWorker(QtCore.QThread):
    """Runs session compaction on a background thread to prevent UI freezes.

    The blocking LLM summarization call is moved off Houdini's main event loop.
    Emits finished_compaction(success: bool, message: str) when done.
    """

    finished_compaction = QtCore.Signal(bool, str)

    def __init__(self, core, session_id, parent=None):
        super().__init__(parent)
        self.core = core
        self.session_id = session_id

    def run(self):
        try:
            success, msg = context_manager.compact_session(self.core, self.session_id)
            self.finished_compaction.emit(success, msg)
        except Exception as e:
            print(f"Error in CompactWorker: {str(e)}")
            self.finished_compaction.emit(False, f"Compaction error: {str(e)}")


class AntiPatternWorker(QtCore.QThread):
    def __init__(
        self, core, error_type, trace, failed_code, fix_description, parent=None
    ):
        super().__init__(parent)
        self.core = core
        self.error_type = error_type
        self.trace = trace
        self.failed_code = failed_code
        self.fix_description = fix_description

    def run(self):
        try:
            from memory_db import save_anti_pattern

            embedding = self.core.generate_embedding(self.trace[:1500])
            save_anti_pattern(
                self.core.db_path,
                self.error_type,
                self.trace,
                self.failed_code,
                self.fix_description,
                embedding,
            )
        except Exception as e:
            print(f"Failed to log anti-pattern: {e}")
