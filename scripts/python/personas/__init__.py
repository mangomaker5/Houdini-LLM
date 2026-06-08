import importlib


def get_persona_prompt(persona_name):
    """
    Dynamically loads the system prompt for a given persona.
    """
    # Map the human-readable names to module names
    persona_map = {
        "General TD": "general_td",
        "Arnold Expert": "arnold_expert",
        "Solaris/USD Expert": "solaris_expert",
        "FX Expert": "fx_expert",
    }

    module_name = persona_map.get(persona_name, "general_td")

    try:
        module = importlib.import_module(f"personas.{module_name}")
        return module.SYSTEM_PROMPT
    except Exception as e:
        print(f"Error loading persona {persona_name}: {e}")
        return "You are an AI Assistant for Houdini."
