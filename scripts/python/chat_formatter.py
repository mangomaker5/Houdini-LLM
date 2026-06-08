import re


def format_markdown_to_html(text):
    text = text.replace("<", "&lt;").replace(">", "&gt;")

    def format_code_block(match):
        code = match.group(1).strip()
        return f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" bgcolor="#1e1e1e" style="margin-top: 15px; margin-bottom: 15px; border-radius: 6px;">
            <tr>
                <td bgcolor="#2b2b2b" style="padding: 5px 10px; border-bottom: 1px solid #444444;">
                    <div style="color: #aaaaaa; font-size: 12px; font-weight: bold;">PYTHON</div>
                </td>
            </tr>
            <tr>
                <td style="padding: 10px;">
                    <pre style="color: #cccccc; font-family: 'Consolas', 'Courier New', monospace; font-size: 13px; margin: 0;">{code}</pre>
                </td>
            </tr>
        </table>
        """

    text = re.sub(
        r"```python\n?(.*?)(?:```|$)",
        format_code_block,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    text = text.replace("\n", "<br/>")

    text = re.sub(
        r"(?:<br/>\s*)*___TOOL_EXEC_(.*?)___(?:<br/>\s*)*",
        r"<div style='color: #888888; font-style: italic; font-size: 11px; margin: 4px 0px; background-color: #2b2b2b; padding: 2px 8px; border-radius: 4px; display: inline-block;'>⚙ Executing tool: <b>\1</b></div><br/>",
        text,
    )

    return text


def build_bubble(role, text, show_header=True):
    # Special Check for Model Change system message
    if role == "System" and "Switched model to" in text:
        return f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 15px;">
            <tr>
                <td align="center">
                    <div style="border-left: 2px solid #555; padding-left: 10px; color: #888; font-size: 12px; font-style: italic;">
                        {text}
                    </div>
                </td>
            </tr>
        </table>
        """
    elif role == "System" and "Switched persona to" in text:
        return f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 15px;">
            <tr>
                <td align="center">
                    <div style="border-left: 2px solid #f1c40f; padding-left: 10px; color: #f1c40f; font-size: 12px; font-weight: bold;">
                        ⚠️ {text}
                    </div>
                </td>
            </tr>
        </table>
        """

    html_content = format_markdown_to_html(text)

    if role == "User":
        return f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 25px;">
            <tr>
                <td width="30%"></td>
                <td align="right">
                    <div style="font-weight: bold; color: #4daafc; margin-bottom: 8px; font-size: 13px;">Human</div>
                    <table border="0" cellpadding="14" cellspacing="0" bgcolor="#383838" style="border-radius: 18px;">
                        <tr>
                            <td align="left" style="color: #dfdfdf; font-size: 14px; line-height: 1.6;">
                                {html_content}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        """
    elif role in ("Agent", "Agent (MCP)"):
        if role == "Agent":
            title = "◆ HOUDINI-LLM"
            color = "#19c37d"
        else:
            title = "⚡ Agent Mode Auto"
            color = "#f1c40f"

        header_html = (
            f'<div style="font-weight: bold; color: {color}; margin-bottom: 8px; font-size: 15px;">{title}</div>'
            if show_header
            else ""
        )

        return f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 5px; margin-bottom: 25px;">
            <tr>
                <td align="left">
                    {header_html}
                    <div style="color: #dfdfdf; line-height: 1.6; font-size: 14px;">
                        {html_content}
                    </div>
                </td>
            </tr>
        </table>
        """
    else:  # System or Thinking
        color = "#ab68ff" if role == "Thinking" else "#aaaaaa"
        return f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 25px;">
            <tr>
                <td align="left">
                    <div style="font-weight: bold; color: {color}; margin-bottom: 8px; font-size: 15px;">◆ System</div>
                    <div style="color: {color}; line-height: 1.6; font-size: 14px;">
                        <i>{html_content}</i>
                    </div>
                </td>
            </tr>
        </table>
        """
