# Optional import to allow testing outside of Houdini
try:
    import hou

    HOUDINI_AVAILABLE = True
except ImportError:
    HOUDINI_AVAILABLE = False


class HoudiniContext:
    def __init__(self):
        pass

    def get_selected_nodes_context(self):
        """Returns a string describing the currently selected nodes."""
        if not HOUDINI_AVAILABLE:
            return "Not running inside Houdini."

        selected = hou.selectedNodes()
        if not selected:
            return "No nodes currently selected."

        context_lines = ["### Selected Nodes Context ###"]
        for node in selected:
            context_lines.append(f"\nNode: {node.path()}")
            context_lines.append(f"Type: {node.type().name()}")

            # Get common parameters (ignoring hidden/read-only to save space)
            context_lines.append("Parameters:")
            for parm in node.parms():
                if not parm.isHidden() and not parm.isDisabled():
                    try:
                        # Use unexpandedString instead of eval() to completely avoid triggering slow geometry cooks!
                        val = parm.unexpandedString()
                        # Truncate long strings
                        if isinstance(val, str) and len(val) > 100:
                            val = val[:100] + "..."
                        context_lines.append(
                            f"  - {parm.name()} ({parm.description()}): {val}"
                        )
                    except Exception:
                        pass
        return "\n".join(context_lines)

    def generate_system_prompt(self):
        """Generates the system instruction prompt for the LLM."""
        prompt = (
            "You are a Houdini TD (Technical Director) AI Agent. "
            "You write Python scripts using the `hou` module to automate tasks, set up rendering rigs (like Karma/Mantra), "
            "assign materials, and organize scenes. "
            "IMPORTANT RULES:\n"
            "1. When writing code to modify the scene, ALWAYS wrap your Python code in standard markdown ```python blocks.\n"
            "2. Ensure all parameter names match the exact internal names provided in the context.\n"
            "3. Do not include `import hou` inside your code blocks, as it is already provided.\n"
            "4. Keep explanations brief. Focus on the code."
        )
        return prompt
