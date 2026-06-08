import re
import traceback

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
                        val = parm.eval()
                        # Truncate long strings
                        if isinstance(val, str) and len(val) > 100:
                            val = val[:100] + "..."
                        context_lines.append(f"  - {parm.name()} ({parm.description()}): {val}")
                    except:
                        pass
        return "\n".join(context_lines)

    def extract_and_execute_code(self, response_text):
        """
        Parses python code blocks from the LLM response and executes them.
        Returns a tuple (success: bool, output/error message: str).
        """
        if not HOUDINI_AVAILABLE:
            return False, "Cannot execute code outside of Houdini."

        # Find markdown python blocks
        code_blocks = re.findall(r"```python\n(.*?)\n```", response_text, re.DOTALL)
        
        if not code_blocks:
            return False, "No Python code found to execute."

        results = []
        for i, code in enumerate(code_blocks):
            try:
                # We use exec() to run the code. We provide the 'hou' module in the globals dict
                # so the script can use it.
                exec_globals = {"hou": hou}
                exec(code, exec_globals)
                results.append(f"Block {i+1} executed successfully.")
            except Exception as e:
                err_msg = traceback.format_exc()
                results.append(f"Error in Block {i+1}:\n{err_msg}")
                return False, "\n".join(results) # Stop on first error

        return True, "\n".join(results)

    def execute_code_block(self, code_text):
        """Executes a single raw Python code string."""
        if not HOUDINI_AVAILABLE:
            return False, "Cannot execute code outside of Houdini."
            
        try:
            exec_globals = {"hou": hou}
            exec(code_text, exec_globals)
            return True, "Code executed successfully."
        except Exception as e:
            err_msg = traceback.format_exc()
            return False, f"Execution Error:\n{err_msg}"

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
