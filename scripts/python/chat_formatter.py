import re

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import HtmlFormatter

    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


def format_markdown_to_html(
    text, code_blocks_store=None, action_states=None, show_actions=True
):
    if code_blocks_store is None:
        code_blocks_store = {}
    if action_states is None:
        action_states = {}

    if text is None:
        return ""
    text = str(text)
    text = text.replace("<", "&lt;").replace(">", "&gt;")

    blocks = []

    def save_generic_block(match):
        code = match.group(2).strip()
        lang = match.group(1).strip().upper() if match.group(1) else "CODE"

        display_code = code
        if HAS_PYGMENTS:
            try:
                lexer_name = match.group(1).strip().lower() if match.group(1) else ""
                if lexer_name:
                    lexer = get_lexer_by_name(lexer_name, stripall=True)
                else:
                    lexer = guess_lexer(code)
                formatter = HtmlFormatter(style="monokai", noclasses=True)
                highlighted = highlight(code, lexer, formatter)
                pre_match = re.search(
                    r"<pre[^>]*>(.*?)</pre>",
                    highlighted,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                if pre_match:
                    display_code = pre_match.group(1)
            except Exception:
                pass

        block_id = f"block_{len(code_blocks_store)}"
        code_blocks_store[block_id] = code

        run_text = action_states.get(f"run_code:{block_id}", "&nbsp;▶ Run Code&nbsp;")
        copy_text = action_states.get(
            f"copy_code:{block_id}", "&nbsp;📋 Copy Code&nbsp;"
        )
        save_text = action_states.get(
            f"save_code:{block_id}", "&nbsp;🌟 Save to Memory&nbsp;"
        )

        run_color = (
            "#ffffff"
            if ("Success" in run_text or "Error" in run_text or "Failed" in run_text)
            else "#19c37d"
        )
        run_bg = (
            "#19c37d"
            if "Success" in run_text
            else (
                "#ff4a4a"
                if ("Error" in run_text or "Failed" in run_text)
                else "#444444"
            )
        )
        copy_color = "#19c37d" if "Copied" in copy_text else "#dfdfdf"
        save_color = (
            "#19c37d"
            if "Saved" in save_text
            else ("#ff4a4a" if "Failed" in save_text else "#f1c40f")
        )

        actions_html = ""
        if show_actions and lang == "PYTHON":
            actions_html = f'''
                                <table border="0" cellpadding="4" cellspacing="0">
                                    <tr>
                                        <td bgcolor="#444444" style="border-radius: 4px;">
                                            <a href="save_code:{block_id}" style="color: {save_color}; text-decoration: none;">{save_text}</a>
                                        </td>
                                        <td width="5"></td>
                                        <td bgcolor="{run_bg}" style="border-radius: 4px;">
                                            <a href="run_code:{block_id}" style="color: {run_color}; text-decoration: none;">{run_text}</a>
                                        </td>
                                        <td width="5"></td>
                                        <td bgcolor="#444444" style="border-radius: 4px;">
                                            <a href="copy_code:{block_id}" style="color: {copy_color}; text-decoration: none;">{copy_text}</a>
                                        </td>
                                    </tr>
                                </table>
            '''

        html = f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" bgcolor="#1e1e1e" style="margin-top: 15px; margin-bottom: 15px; border-radius: 6px;">
            <tr>
                <td bgcolor="#2b2b2b" style="padding: 5px 10px; border-bottom: 1px solid #444444;">
                    <table width="100%" border="0" cellpadding="0" cellspacing="0">
                        <tr>
                            <td align="left" style="color: #aaaaaa; font-size: 12px; font-weight: bold;">{lang}</td>
                            <td align="right" style="font-size: 11px; font-weight: bold;">
                                {actions_html}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td style="padding: 10px;">
                    <pre style="color: #cccccc; font-family: 'Consolas', 'Courier New', monospace; font-size: 13px; margin: 0; white-space: pre-wrap; word-wrap: break-word;">{display_code}</pre>
                </td>
            </tr>
        </table>
        """
        blocks.append(html)
        return f"@@@BLOCK_{len(blocks) - 1}@@@"

    # Match all code blocks: ```language ... ```
    text = re.sub(
        r"```(\w*)\n?(.*?)(?:```|$)",
        save_generic_block,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Format Tool Execution tags BEFORE markdown
    text = re.sub(
        r"(?:\n\s*)*___TOOL_EXEC_(.*?)___(?:\n\s*)*",
        r"\n\n<div style='color: #888888; font-style: italic; font-size: 11px; margin: 4px 0px; background-color: #2b2b2b; padding: 2px 8px; border-radius: 4px; display: inline-block;'>⚙ Executing tool: <b>\1</b></div>\n\n",
        text,
    )

    # Parse markdown to HTML
    try:
        import markdown

        text = markdown.markdown(text, extensions=["tables", "sane_lists"])
        # Enhance PySide6 table rendering
        text = text.replace(
            "<table>",
            '<table border="1" cellspacing="0" cellpadding="4" style="border-collapse: collapse; border-color: #555555; margin-top: 10px; margin-bottom: 10px;">',
        )
        text = text.replace("<th>", '<th bgcolor="#333333" style="padding: 5px;">')
        text = text.replace("<td>", '<td style="padding: 5px;">')
    except ImportError:
        text = text.replace("\n", "<br/>")

    # Restore the code blocks
    for i, html in enumerate(blocks):
        text = text.replace(f"@@@BLOCK_{i}@@@", html)

    return text


def build_bubble(
    role, text, code_blocks_store=None, action_states=None, show_header=True
):
    if code_blocks_store is None:
        code_blocks_store = {}
    if action_states is None:
        action_states = {}

    if text is None:
        text = ""
    else:
        text = str(text)

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

    is_agent = role in ("Agent", "Agent (MCP)")
    html_content = format_markdown_to_html(
        text, code_blocks_store, action_states, show_actions=is_agent
    )

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
                    <table border="0" cellpadding="14" cellspacing="0" bgcolor="#2b2b2b" style="border-radius: 18px;">
                        <tr>
                            <td align="left" style="color: #dfdfdf; font-size: 14px; line-height: 1.6;">
                                {html_content}
                            </td>
                        </tr>
                    </table>
                </td>
                <td width="10%"></td>
            </tr>
        </table>
        """
    elif role == "Agent Status":
        return f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 25px;">
            <tr>
                <td align="left">
                    <div style="font-weight: bold; margin-bottom: 8px; font-size: 15px;">{text}</div>
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
