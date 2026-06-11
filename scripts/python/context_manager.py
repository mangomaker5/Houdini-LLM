import re

import database


def estimate_tokens(text):
    """A fast heuristic to estimate token count (roughly 4 chars per token)."""
    if not text:
        return 0
    return len(text) // 4


def calculate_session_usage(db_path, session_id):
    """Calculates the current token usage for a session."""
    session_details = database.get_session_details(db_path, session_id)
    if not session_details:
        return 0, 128000, 0.0

    token_limit = session_details.get("token_limit", 128000)
    summary = session_details.get("summary", "")

    messages = database.get_messages(db_path, session_id)

    total_text = summary
    for msg in messages:
        total_text += msg.get("content", "")

    current_tokens = estimate_tokens(total_text)

    usage_percentage = 0.0
    if token_limit > 0:
        usage_percentage = (current_tokens / token_limit) * 100.0

    return current_tokens, token_limit, usage_percentage


# ---------------------------------------------------------------------------
# Pre-processing: Strip code blocks & tool outputs before summarization
# ---------------------------------------------------------------------------

# Matches fenced code blocks: ```lang ... ``` (greedy, DOTALL)
_CODE_BLOCK_RE = re.compile(r"```[\w]*\n.*?```", re.DOTALL)

# Matches inline tool execution markers injected by core.py
_TOOL_EXEC_RE = re.compile(r"___TOOL_EXEC_\w+___")


def _strip_heavy_content(text):
    """Replace large code blocks and tool markers with lightweight tombstones.

    This keeps the summarizer focused on conversational milestones and decisions
    rather than burning tokens on raw Python/VEX syntax that is already
    preserved permanently in the Vector DB (Learned Skills & Anti-Patterns).
    """
    # Replace fenced code blocks with a tombstone
    text = _CODE_BLOCK_RE.sub("[Code Block Removed — Preserved in Memory]", text)

    # Replace tool execution markers with a clean tag
    text = _TOOL_EXEC_RE.sub("[Tool Executed]", text)

    return text


def compact_session(core_ref, session_id, keep_last_n=5):
    """
    Summarizes the oldest messages in the session to free up context window.
    Returns (success_bool, status_message).
    """
    db_path = core_ref.db_path

    session_details = database.get_session_details(db_path, session_id)
    if not session_details:
        return False, "Session not found."

    messages = database.get_messages(db_path, session_id)

    if len(messages) <= keep_last_n + 2:
        return False, "Not enough messages to compact."

    old_summary = session_details.get("summary", "")

    # Extract the messages we want to summarize (everything before the last N)
    messages_to_summarize = messages[:-keep_last_n]

    # Filter out meta-messages that should never be summarized
    _SKIP_PREFIXES = (
        "/compact", "/usage",                       # Slash commands
        "**📊 Usage Report",                        # /usage output
        "⏳ Compacting", "Running manual compaction", # Compact status
        "--- Switched model to",                     # Model switch notices
    )

    # Prepare the prompt for the LLM
    text_to_summarize = []
    for msg in messages_to_summarize:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if any(content.startswith(prefix) for prefix in _SKIP_PREFIXES):
            continue
        text_to_summarize.append(f"[{role.upper()}]: {content}")

    joined_text = "\n\n".join(text_to_summarize)

    # --- Smart pre-processing: strip code blocks & tool noise ---
    joined_text = _strip_heavy_content(joined_text)

    system_prompt = (
        "You are an expert technical summarizer for a Houdini AI Agent system. "
        "Your goal is to compress the provided chat history into a concise, dense summary.\n"
        "IMPORTANT RULES:\n"
        "1. Focus on HIGH-LEVEL MILESTONES: what the user asked for, what decisions were made, "
        "what succeeded, and what failed.\n"
        "2. Do NOT attempt to reproduce any code syntax. Code is already preserved in "
        "the agent's long-term Vector DB memory (Learned Skills & Anti-Patterns).\n"
        "3. Retain key facts: node paths, parameter names, error types, and technical decisions.\n"
        "4. Discard conversational filler, pleasantries, and verbose formatting.\n"
        "5. Combine the 'Previous Summary' with the 'New Messages' into one single "
        "unified summary as a bulleted list of milestones.\n"
    )

    user_prompt = (
        f"--- PREVIOUS SUMMARY ---\n{old_summary}\n\n"
        f"--- NEW MESSAGES TO SUMMARIZE ---\n{joined_text}\n\n"
        "Please provide the updated, unified summary now."
    )

    # Call the LLM synchronously (caller is responsible for threading)
    try:
        new_summary = core_ref.generate_response_sync(
            user_prompt, system_context=system_prompt
        )

        if not new_summary or new_summary.startswith("Error:"):
            return False, f"Summarization failed: {new_summary}"

        # Update DB
        database.update_session_summary(db_path, session_id, new_summary)
        database.delete_oldest_messages(db_path, session_id, keep_last_n)

        return True, "Context compacted successfully."

    except Exception as e:
        return False, f"Summarization error: {str(e)}"
