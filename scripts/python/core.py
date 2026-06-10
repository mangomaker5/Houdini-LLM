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

    def append_to_history(self, role, content):
        if self.session_id:
            database.add_message(self.db_path, self.session_id, role, content)

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
            with urllib.request.urlopen(req, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
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
                with urllib.request.urlopen(req, timeout=20) as response:
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

                    for tc in tool_calls_buffer.values():
                        if check_cancelled and check_cancelled():
                            break
                        f_name = tc["function"]["name"]
                        f_args = tc["function"]["arguments"]

                        tool_msg = f"\n___TOOL_EXEC_{f_name}___\n"
                        complete_response += tool_msg

                        # Do NOT yield tool_msg to the UI. Instead, send a status update.
                        if "on_status_update" in kwargs:
                            status_map = {
                                "search_memory": (
                                    "🧠 Searching Knowledge Base",
                                    "#9b59b6",
                                ),
                                "search_api_docs": (
                                    "📚 Querying Houdini Docs",
                                    "#3498db",
                                ),
                                "get_node_parameters": (
                                    "👁️ Inspecting Live Scene",
                                    "#e67e22",
                                ),
                                "analyze_node_type": (
                                    "🔍 Analyzing Node Constraints",
                                    "#f1c40f",
                                ),
                                "propose_code_change": (
                                    "✍️ Synthesizing Python Script",
                                    "#2ecc71",
                                ),
                            }
                            msg, color = status_map.get(
                                f_name, (f"✨ Running {f_name}", "#95a5a6")
                            )
                            kwargs["on_status_update"](msg, color)

                        result = mcp_tools.execute_tool(f_name, f_args)

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
                    self.append_to_history(role_to_save, complete_response)
                break

            except urllib.error.HTTPError as e:
                error_msg = e.read().decode("utf-8")
                msg = f"\nAPI Error ({e.code}): {error_msg}"
                print(f"Network Error: {msg}")
                role_to_save = "assistant_mcp" if agent_mode else "assistant"
                self.append_to_history(role_to_save, msg)
                yield msg
                break
            except Exception as e:
                msg = f"\nConnection Error: {str(e)}"
                print(f"Network Error: {msg}")
                role_to_save = "assistant_mcp" if agent_mode else "assistant"
                self.append_to_history(role_to_save, msg)
                yield msg
                break
