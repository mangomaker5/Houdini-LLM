import re

def format_markdown_to_html(text, code_blocks_store, action_states):
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    
    code_blocks = []
    def save_code_block(match):
        code = match.group(1).strip()
        code_blocks.append(code)
        return f"___CODE_BLOCK_{len(code_blocks)-1}___"
        
    text = re.sub(r"```(?:python)?\n?(.*?)(?:```|$)", save_code_block, text, flags=re.DOTALL)
    text = text.replace("\n", "<br/>")
    
    for i, code in enumerate(code_blocks):
        block_id = f"block_{len(code_blocks_store)}"
        code_blocks_store[block_id] = code
        
        run_text = action_states.get(f"run_code:{block_id}", "&nbsp;▶ Run Code&nbsp;")
        copy_text = action_states.get(f"copy_code:{block_id}", "&nbsp;📋 Copy Code&nbsp;")
        
        run_color = "#ffffff" if ("Success" in run_text or "Error" in run_text) else "#19c37d"
        run_bg = "#19c37d" if "Success" in run_text else ("#ff4a4a" if "Error" in run_text else "#444444")
        copy_color = "#19c37d" if "Copied" in copy_text else "#dfdfdf"
        
        html = f'''
        <table width="100%" border="0" cellpadding="0" cellspacing="0" bgcolor="#1e1e1e" style="margin-top: 15px; margin-bottom: 15px; border-radius: 6px;">
            <tr>
                <td bgcolor="#2b2b2b" style="padding: 5px 10px; border-bottom: 1px solid #444444;">
                    <table width="100%" border="0" cellpadding="0" cellspacing="0">
                        <tr>
                            <td align="left" style="color: #aaaaaa; font-size: 12px; font-weight: bold;">PYTHON</td>
                            <td align="right" style="font-size: 11px; font-weight: bold;">
                                <table border="0" cellpadding="4" cellspacing="0">
                                    <tr>
                                        <td bgcolor="{run_bg}" style="border-radius: 4px;">
                                            <a href="run_code:{block_id}" style="color: {run_color}; text-decoration: none;">{run_text}</a>
                                        </td>
                                        <td width="5"></td>
                                        <td bgcolor="#444444" style="border-radius: 4px;">
                                            <a href="copy_code:{block_id}" style="color: {copy_color}; text-decoration: none;">{copy_text}</a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td style="padding: 10px;">
                    <pre style="color: #cccccc; font-family: 'Consolas', 'Courier New', monospace; font-size: 13px; margin: 0;">{code}</pre>
                </td>
            </tr>
        </table>
        '''
        text = text.replace(f"___CODE_BLOCK_{i}___", html)
        
    return text

def build_bubble(role, text, code_blocks_store, action_states):
    # Special Check for Model Change system message
    if role == "System" and "Switched model to" in text:
        return f'''
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 15px;">
            <tr>
                <td align="center">
                    <div style="border-left: 2px solid #555; padding-left: 10px; color: #888; font-size: 12px; font-style: italic;">
                        {text}
                    </div>
                </td>
            </tr>
        </table>
        '''

    html_content = format_markdown_to_html(text, code_blocks_store, action_states)
    
    if role == "User":
        return f'''
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 25px;">
            <tr>
                <td width="30%"></td>
                <td align="right">
                    <div style="font-weight: bold; color: #aaaaaa; margin-bottom: 8px; font-size: 13px;">Human</div>
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
        '''
    elif role in ("Agent", "Agent (MCP)"):
        if role == "Agent":
            title = "◆ HOUDINI-LLM"
            color = "#19c37d"
        else:
            title = "⚡ Agent Mode MCP"
            color = "#f1c40f"
            
        return f'''
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 25px;">
            <tr>
                <td align="left">
                    <div style="font-weight: bold; color: {color}; margin-bottom: 8px; font-size: 15px;">{title}</div>
                    <div style="color: #dfdfdf; line-height: 1.6; font-size: 14px;">
                        {html_content}
                    </div>
                </td>
            </tr>
        </table>
        '''
    else: # System or Thinking
        color = "#ab68ff" if role == "Thinking" else "#aaaaaa"
        return f'''
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
        '''
