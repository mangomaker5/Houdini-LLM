from styles import THEME

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def get_spinner_frame(tick_count):
    """Return the current frame of the Braille spinner based on tick_count."""
    return SPINNER_FRAMES[tick_count % len(SPINNER_FRAMES)]


def render_dynamic_agent_status(tick_count, status_text, color=None):
    """
    Renders a compact, high-quality CLI-style loading badge.
    E.g.: ⠋ Thinking...
    """
    if not color:
        color = THEME["info"]

    spinner = get_spinner_frame(tick_count)

    # Render a clean HTML block for the status
    styled_role = (
        f"<span style='color: {color}; font-family: monospace; font-size: 18px; margin-right: 8px; font-weight: bold;'>"
        f"{spinner}</span>"
        f"<span style='color: {color}; font-weight: bold;'>{status_text}</span>"
    )
    return styled_role
