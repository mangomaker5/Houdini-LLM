import os
import json
import urllib.request
import urllib.error
import uuid

import database


class AIAgentCore:
    def __init__(self, api_key="", model="deepseek/deepseek-v4-pro"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.session_id = None

        # Determine the memory directory dynamically based on user home
        user_home = os.path.expanduser("~")
        self.memory_dir = os.path.join(user_home, "houdini_ai_agent_memory")
        if not os.path.exists(self.memory_dir):
            os.makedirs(self.memory_dir)

        # Initialize SQLite Database
        self.db_path = database.init_db(self.memory_dir)

        self.config_file = os.path.join(self.memory_dir, "config.json")

        self.load_config()

        # Load the latest session if available
        sessions = self.get_all_sessions()
        if sessions:
            self.load_session(sessions[0]["id"])

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                    if not self.api_key:
                        self.api_key = config.get("api_key", "")
            except Exception as e:
                print(f"Error loading config: {e}")

    def delete_config(self):
        self.api_key = ""
        self.model = "deepseek/deepseek-v4-pro"
        if os.path.exists(self.config_file):
            try:
                os.remove(self.config_file)
            except Exception as e:
                print(f"Error deleting config: {e}")

    def save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump({"api_key": self.api_key}, f)
        except Exception as e:
            print(f"Error saving config: {e}")

    def set_api_key(self, key):
        self.api_key = key
        self.save_config()

    def set_model(self, model):
        self.model = model

    def start_new_session(self):
        self.session_id = str(uuid.uuid4())[:8]
        database.create_session(self.db_path, self.session_id, "New Chat")

    def get_all_sessions(self):
        return database.get_all_sessions(self.db_path)

    def delete_session(self, session_id):
        success = database.delete_session(self.db_path, session_id)
        if success and self.session_id == session_id:
            self.session_id = None
            sessions = self.get_all_sessions()
            if sessions:
                self.load_session(sessions[0]["id"])
        return success

    def rename_session(self, session_id, new_title):
        database.rename_session(self.db_path, session_id, new_title)

    def load_session(self, session_id):
        details = database.get_session_details(self.db_path, session_id)
        if details:
            self.session_id = session_id
            return True
        return False

    def get_chat_history(self):
        if not self.session_id:
            return []
        return database.get_messages(self.db_path, self.session_id)

    def append_to_history(self, role, content, prompt_tokens=0, completion_tokens=0):
        if self.session_id:
            database.add_message(
                self.db_path,
                self.session_id,
                role,
                content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

            # If this is the first user message, rename the session title automatically
            if role == "user":
                messages = database.get_messages(self.db_path, self.session_id)
                user_msgs = [m for m in messages if m["role"] == "user"]
                if (
                    len(user_msgs) == 1
                ):  # Only rename if it's the very first user message
                    new_title = content[:20] + ("..." if len(content) > 20 else "")
                    self.rename_session(self.session_id, new_title)

    def fetch_models(self):
        """Fetches available models dynamically from OpenRouter API"""
        if not self.api_key:
            return ["deepseek/deepseek-v4-pro"]

        url = "https://openrouter.ai/api/v1/models"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "data" in result:
                    models = [m["id"] for m in result["data"]]
                    return sorted(models)
        except Exception as e:
            print(f"Error fetching models: {e}")
        return ["deepseek/deepseek-v4-pro"]

    def _prepare_request_history(self, system_context):
        if not self.session_id:
            self.start_new_session()

        session_details = database.get_session_details(self.db_path, self.session_id)
        summary = session_details.get("summary", "") if session_details else ""

        request_history = []

        # 1. Add System Context
        if system_context:
            request_history.append({"role": "system", "content": system_context})

        # 2. Add Persistent Summary (if any) as a system instruction
        if summary:
            request_history.append(
                {
                    "role": "system",
                    "content": f"Previous conversation summary context:\n{summary}",
                }
            )

        # 3. Add recent messages from DB (this now includes the user message we just saved)
        messages = database.get_messages(self.db_path, self.session_id)
        for msg in messages:
            # UI status messages are stored as 'system' in the DB. They must not be sent to the API.
            if msg["role"] == "system":
                continue

            role_for_api = (
                "assistant" if msg["role"] == "assistant_mcp" else msg["role"]
            )
            request_history.append({"role": role_for_api, "content": msg["content"]})

        return request_history

    def generate_embedding(self, text):
        """Generates a 1536-dimensional embedding using OpenRouter's text-embedding-3-small."""
        if not self.api_key:
            raise ValueError("No OpenRouter API key provided.")

        url = "https://openrouter.ai/api/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {"input": text, "model": "openai/text-embedding-3-small"}

        import time
        import urllib.error

        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(data).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=20) as response:
                    res = json.loads(response.read().decode("utf-8"))

                    # Log embedding usage for billing
                    usage = res.get("usage", {})
                    if usage:
                        database.log_usage(
                            self.db_path,
                            self.session_id,
                            "embedding",
                            "openai/text-embedding-3-small",
                            usage.get("prompt_tokens", 0),
                            0,
                            usage.get("total_tokens", 0),
                            usage.get("cost", 0.0),
                        )

                    return res["data"][0]["embedding"]
            except urllib.error.HTTPError as e:
                if attempt == 2:
                    raise
                print(
                    f"\n[Warning] API HTTP Error {e.code}: {e.reason}. Retrying ({attempt + 1}/3)..."
                )
                retry_after = e.headers.get("Retry-After")
                time.sleep(int(retry_after) + 1 if retry_after else 2)
            except Exception as e:
                if attempt == 2:
                    raise
                print(
                    f"\n[Warning] API Connection Error: {e}. Retrying ({attempt + 1}/3)..."
                )
                time.sleep(2)

    def generate_response_sync(self, user_message, system_context=""):
        """Synchronous version for summarization background tasks."""
        if not self.api_key:
            return "Error: No API key."

        request_history = []
        if system_context:
            request_history.append({"role": "system", "content": system_context})
        request_history.append({"role": "user", "content": user_message})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {"model": self.model, "messages": request_history, "stream": False}

        try:
            req = urllib.request.Request(
                self.base_url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))

                # Log usage for billing
                usage = result.get("usage", {})
                if usage:
                    database.log_usage(
                        self.db_path,
                        self.session_id,
                        "summary",
                        self.model,
                        usage.get("prompt_tokens", 0),
                        usage.get("completion_tokens", 0),
                        usage.get("total_tokens", 0),
                        usage.get("cost", 0.0),
                    )

                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                return "Error: Empty response."
        except Exception as e:
            return f"Error: {str(e)}"

    def generate_response_stream(
        self,
        user_message,
        system_context="",
        agent_mode=False,
        check_cancelled=None,
        **kwargs,
    ):
        if not self.api_key:
            yield "Error: Please set your OpenRouter API key in settings."
            return

        request_history = self._prepare_request_history(system_context)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if agent_mode:
            import mcp_tools

        complete_response = ""
        syntax_retries = 0
        pipeline_retries = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0

        # Loop to support multiple tool call iterations
        while True:
            if check_cancelled and check_cancelled():
                break

            data = {"model": self.model, "messages": request_history, "stream": True}
            if agent_mode:
                data["tools"] = mcp_tools.AGENT_TOOLS_SCHEMA

            full_reply = ""
            tool_calls_buffer = {}

            try:
                req = urllib.request.Request(
                    self.base_url,
                    data=json.dumps(data).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=120) as response:
                    while True:
                        if check_cancelled and check_cancelled():
                            break
                        line = response.readline()
                        if not line:
                            break
                        line = line.decode("utf-8").strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            json_str = line[6:]
                            if json_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(json_str)
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    delta = chunk["choices"][0].get("delta", {})

                                    # Text content
                                    content = delta.get("content", "")
                                    if content:
                                        full_reply += content
                                        complete_response += content
                                        yield content

                                    # Tool calls
                                    if "tool_calls" in delta:
                                        for tc in delta["tool_calls"]:
                                            idx = tc.get("index")
                                            if idx not in tool_calls_buffer:
                                                tool_calls_buffer[idx] = {
                                                    "id": tc.get("id", ""),
                                                    "type": "function",
                                                    "function": {
                                                        "name": "",
                                                        "arguments": "",
                                                    },
                                                }
                                            if "id" in tc and tc["id"]:
                                                tool_calls_buffer[idx]["id"] = tc["id"]
                                            if "function" in tc:
                                                f = tc["function"]
                                                if "name" in f and f["name"]:
                                                    tool_calls_buffer[idx]["function"][
                                                        "name"
                                                    ] += f["name"]
                                                if "arguments" in f and f["arguments"]:
                                                    tool_calls_buffer[idx]["function"][
                                                        "arguments"
                                                    ] += f["arguments"]

                                # Capture usage from final chunk (separate from choices)
                                if "usage" in chunk:
                                    usage = chunk["usage"]
                                    round_prompt = usage.get("prompt_tokens", 0)
                                    round_completion = usage.get("completion_tokens", 0)
                                    round_total = usage.get("total_tokens", 0)
                                    round_cost = usage.get("cost", 0.0)
                                    total_prompt_tokens += round_prompt
                                    total_completion_tokens += round_completion
                                    database.log_usage(
                                        self.db_path,
                                        self.session_id,
                                        "chat",
                                        self.model,
                                        round_prompt,
                                        round_completion,
                                        round_total,
                                        round_cost,
                                    )

                            except Exception as e:
                                print(f"Error parsing chunk: {e}")

                if check_cancelled and check_cancelled():
                    break

                # If there are tool calls to process
                if tool_calls_buffer:
                    assistant_msg = {
                        "role": "assistant",
                        "content": full_reply if full_reply else None,
                        "tool_calls": list(tool_calls_buffer.values()),
                    }
                    request_history.append(assistant_msg)

                    has_searched = False
                    has_inspected_scene = False

                    for msg in reversed(request_history):
                        if msg.get("role") == "user":
                            break
                        if msg.get("role") == "tool":
                            if msg.get("name") in ["search_memory", "search_api_docs"]:
                                has_searched = True
                            if msg.get("name") in [
                                "get_node_parameters",
                                "analyze_node_type",
                            ]:
                                has_inspected_scene = True

                    for tc in tool_calls_buffer.values():
                        if check_cancelled and check_cancelled():
                            break
                        f_name = tc["function"]["name"]
                        f_args = tc["function"]["arguments"]

                        if f_name == "propose_code_change" and not (
                            has_searched and has_inspected_scene
                        ):
                            pipeline_retries += 1
                            if pipeline_retries >= 2:
                                msg = "\n\n❌ **Agent repeatedly failed to follow the strict inspection pipeline. Halting to save tokens. Please clarify your prompt.**"
                                complete_response += msg
                                yield msg
                                return

                            print(
                                "[Houdini-LLM Warning] Blocked 'propose_code_change' because agent skipped inspection tools."
                            )

                            result = json.dumps(
                                {
                                    "status": "error",
                                    "message": "SYSTEM REJECTION: Strict Pipeline Violation. You attempted to propose code before inspecting. You MUST call search_memory and/or search_api_docs first to gather context. Do not guess.",
                                    "instruction": "Execute the required search tools first, read their output, and then propose the code.",
                                }
                            )

                            request_history.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "name": f_name,
                                    "content": result,
                                }
                            )
                            continue

                        tool_msg = f"\n___TOOL_EXEC_{f_name}___\n"
                        complete_response += tool_msg

                        # Do NOT yield tool_msg to the UI. Instead, send a status update.
                        if "on_status_update" in kwargs:
                            from styles import THEME

                            status_map = {
                                "search_memory": (
                                    "🧠 Searching Knowledge Base",
                                    THEME.get("accent_purple", "#9b59b6"),
                                ),
                                "search_api_docs": (
                                    "📚 Querying Houdini Docs",
                                    THEME.get("info", "#3498db"),
                                ),
                                "get_node_parameters": (
                                    "👁️ Inspecting Live Scene",
                                    THEME.get("warning", "#e67e22"),
                                ),
                                "analyze_node_type": (
                                    "🔍 Analyzing Node Constraints",
                                    THEME.get("accent_yellow", "#f1c40f"),
                                ),
                                "propose_code_change": (
                                    "✍️ Synthesizing Python Script",
                                    THEME.get("success", "#2ecc71"),
                                ),
                            }
                            msg, color = status_map.get(
                                f_name,
                                (
                                    f"✨ Running {f_name}",
                                    THEME.get("text_dim", "#95a5a6"),
                                ),
                            )
                            kwargs["on_status_update"](msg, color)

                        result = mcp_tools.execute_tool(f_name, f_args, core_ref=self)

                        if (
                            f_name == "propose_code_change"
                            and "on_code_proposed" in kwargs
                        ):
                            try:
                                result_dict = json.loads(result)
                                if result_dict.get("status") != "error":
                                    syntax_retries = 0
                                    args_dict = json.loads(f_args)
                                    proposed_code = args_dict.get("python_code", "")
                                    if proposed_code:
                                        kwargs["on_code_proposed"](proposed_code)
                                        injection = (
                                            f"\n\n```python\n{proposed_code}\n```\n\n"
                                        )
                                        complete_response += injection
                                        yield injection
                                else:
                                    syntax_retries += 1
                                    if syntax_retries >= 3:
                                        msg = "\n\n❌ **Agent repeatedly failed pre-flight syntax checks.** Halting to save tokens. Please clarify your prompt."
                                        complete_response += msg
                                        yield msg
                                        return
                            except Exception as e:
                                print(f"Error handling proposed code: {e}")

                        request_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": f_name,
                                "content": result,
                            }
                        )

                    # Continue the while loop to send tool results back to LLM
                    continue

                # If no tool calls, we are completely done
                if complete_response:
                    role_to_save = "assistant_mcp" if agent_mode else "assistant"
                    self.append_to_history(
                        role_to_save,
                        complete_response,
                        prompt_tokens=total_prompt_tokens,
                        completion_tokens=total_completion_tokens,
                    )
                break

            except urllib.error.HTTPError as e:
                error_msg = e.read().decode("utf-8")

                # 1. Print detailed logs to Houdini Console
                print(f"[Houdini-LLM Error] API HTTP {e.code}: {error_msg}")

                # 2. Yield proper error bubble to UI (never saved to DB)
                from styles import THEME

                error_bubble = f"\n\n<div style='color: {THEME['text_main']}; background-color: #3b1e1e; padding: 12px; border-radius: 8px; border: 1px solid {THEME['error']}; margin-top: 10px;'><b>🚨 API Error ({e.code})</b><br><br><span style='font-family: monospace; font-size: 11px; color: {THEME['error']};'>{error_msg}</span></div>"
                yield error_bubble

                # 3. Only save the partial good response to DB
                if complete_response:
                    role_to_save = "assistant_mcp" if agent_mode else "assistant"
                    self.append_to_history(
                        role_to_save,
                        complete_response,
                        prompt_tokens=total_prompt_tokens,
                        completion_tokens=total_completion_tokens,
                    )
                break
            except Exception as e:
                # 1. Print detailed logs to Houdini Console
                print(f"[Houdini-LLM Error] Connection Error: {str(e)}")

                # 2. Yield proper error bubble to UI (never saved to DB)
                from styles import THEME

                error_bubble = f"\n\n<div style='color: {THEME['text_main']}; background-color: #3b1e1e; padding: 12px; border-radius: 8px; border: 1px solid {THEME['error']}; margin-top: 10px;'><b>🚨 Connection Error</b><br><br><span style='font-family: monospace; font-size: 11px; color: {THEME['error']};'>{str(e)}</span></div>"
                yield error_bubble

                # 3. Only save the partial good response to DB
                if complete_response:
                    role_to_save = "assistant_mcp" if agent_mode else "assistant"
                    self.append_to_history(
                        role_to_save,
                        complete_response,
                        prompt_tokens=total_prompt_tokens,
                        completion_tokens=total_completion_tokens,
                    )
                break
