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
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    if not self.api_key:
                        self.api_key = config.get("api_key", "")
            except:
                pass

    def delete_config(self):
        self.api_key = ""
        self.model = "deepseek/deepseek-v4-pro"
        if os.path.exists(self.config_file):
            try:
                os.remove(self.config_file)
            except Exception:
                pass

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump({"api_key": self.api_key}, f)
        except:
            pass

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
                if len(user_msgs) == 1: # Only rename if it's the very first user message
                    new_title = content[:30] + ("..." if len(content) > 30 else "")
                    self.rename_session(self.session_id, new_title)

    def fetch_models(self):
        """Fetches available models dynamically from OpenRouter API"""
        if not self.api_key:
            return ["deepseek/deepseek-v4-pro"]
            
        url = "https://openrouter.ai/api/v1/models"
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                if "data" in result:
                    models = [m["id"] for m in result["data"]]
                    return sorted(models)
        except Exception:
            pass
        return ["deepseek/deepseek-v4-pro"]

    def _prepare_request_history(self, user_message, system_context):
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
            request_history.append({"role": "system", "content": f"Previous conversation summary context:\n{summary}"})
            
        # 3. Add recent messages from DB
        messages = database.get_messages(self.db_path, self.session_id)
        for msg in messages:
            request_history.append({"role": msg["role"], "content": msg["content"]})
            
        # 4. Add the new user message
        request_history.append({"role": "user", "content": user_message})
        
        return request_history

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
            "HTTP-Referer": "https://github.com/sidefx/houdini-agent",
            "X-Title": "Houdini TD Agent",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": request_history,
            "stream": False
        }
        
        try:
            req = urllib.request.Request(
                self.base_url, 
                data=json.dumps(data).encode('utf-8'), 
                headers=headers, 
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                return "Error: Empty response."
        except Exception as e:
            return f"Error: {str(e)}"

    def generate_response_stream(self, user_message, system_context=""):
        if not self.api_key:
            yield "Error: Please set your OpenRouter API key in settings."
            return
            
        request_history = self._prepare_request_history(user_message, system_context)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/sidefx/houdini-agent",
            "X-Title": "Houdini TD Agent",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": request_history,
            "stream": True
        }
        
        full_reply = ""
        
        try:
            req = urllib.request.Request(
                self.base_url, 
                data=json.dumps(data).encode('utf-8'), 
                headers=headers, 
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                while True:
                    line = response.readline()
                    if not line:
                        break
                    line = line.decode('utf-8').strip()
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
                                content = delta.get("content", "")
                                if content:
                                    full_reply += content
                                    yield content
                        except:
                            pass
                            
            if full_reply:
                self.append_to_history("user", user_message)
                self.append_to_history("assistant", full_reply)
        except urllib.error.HTTPError as e:
            error_msg = e.read().decode('utf-8')
            yield f"\nAPI Error ({e.code}): {error_msg}"
        except Exception as e:
            yield f"\nConnection Error: {str(e)}"
