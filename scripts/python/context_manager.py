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
        return 0, 50000, 0.0

    token_limit = session_details.get("token_limit", 50000)
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

    # Prepare the prompt for the LLM
    text_to_summarize = []
    for msg in messages_to_summarize:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        text_to_summarize.append(f"[{role.upper()}]: {content}")

    joined_text = "\n\n".join(text_to_summarize)

    system_prompt = (
        "You are an expert technical summarizer for an AI Assistant system. "
        "Your goal is to compress the provided chat history into a concise, dense summary. "
        "IMPORTANT RULES:\n"
        "1. Retain all key facts, technical decisions, code snippets context, and milestones.\n"
        "2. Discard conversational filler, pleasantries, and verbose formatting.\n"
        "3. Combine the 'Previous Summary' with the 'New Messages' into one single unified summary paragraph or bulleted list.\n"
    )

    user_prompt = (
        f"--- PREVIOUS SUMMARY ---\n{old_summary}\n\n"
        f"--- NEW MESSAGES TO SUMMARIZE ---\n{joined_text}\n\n"
        "Please provide the updated, unified summary now."
    )

    # Call the LLM synchronously
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
