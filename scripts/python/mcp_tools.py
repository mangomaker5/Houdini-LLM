import json
import hou

AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_node_parameters",
            "description": "Fetch the actual parameter names and types for a specific Houdini node type (e.g. 'arnold::standard_surface', 'geo'). Use this before attempting to set parameters to ensure you use the correct internal names. If you get an error that a node type doesn't exist, you may have guessed its name incorrectly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_type": {
                        "type": "string",
                        "description": "The exact Houdini internal node type name to look up.",
                    }
                },
                "required": ["node_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_code_change",
            "description": "Propose python code to be executed within the Houdini session. Use this to construct nodes, set parameters, and modify the scene automatically. The user will review the code before it runs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "python_code": {
                        "type": "string",
                        "description": "The valid Python hou module code to propose.",
                    }
                },
                "required": ["python_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Searches the vector database for past successful code snippets related to the current query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to match against past skills.",
                    }
                },
                "required": ["query"],
            },
        },
    },
]


def _extract_parms(parm_templates, output_dict):
    """Recursively extract parameter templates including inside folders."""
    for pt in parm_templates:
        if pt.type() in (hou.parmTemplateType.FolderSet, hou.parmTemplateType.Folder):
            try:
                _extract_parms(pt.parmTemplates(), output_dict)
            except AttributeError:
                pass
        else:
            output_dict[pt.name()] = {"label": pt.label(), "type": pt.type().name()}


def get_node_parameters(node_type):
    try:
        # Search across all categories for the matching node type
        for cat in hou.nodeTypeCategories().values():
            nt = cat.nodeTypes().get(node_type)
            if nt:
                parm_info = {}
                _extract_parms(nt.parmTemplates(), parm_info)
                return json.dumps(
                    {
                        "status": "success",
                        "node_type": node_type,
                        "parameters": parm_info,
                    }
                )

        return json.dumps(
            {
                "status": "error",
                "message": f"Node type '{node_type}' not found in any category. Are you sure that is the exact internal name?",
            }
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def propose_code_change(python_code):
    return json.dumps(
        {
            "status": "proposed",
            "message": "Code proposed for user review.",
            "code": python_code,
        }
    )


def search_memory(query):
    try:
        from core import AIAgentCore
        from database import search_learned_skills

        core = AIAgentCore()
        embedding = core.generate_embedding(query)
        results = search_learned_skills(core.db_path, embedding, limit=3)
        if not results:
            return json.dumps(
                {"status": "success", "message": "No related skills found in memory."}
            )

        return json.dumps({"status": "success", "results": results})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def execute_tool(tool_name, arguments_json):
    """Dispatches the tool call to the appropriate function."""
    try:
        args = json.loads(arguments_json)
    except json.JSONDecodeError:
        return json.dumps(
            {"status": "error", "message": "Invalid JSON arguments provided to tool."}
        )

    if tool_name == "get_node_parameters":
        return get_node_parameters(args.get("node_type", ""))
    elif tool_name == "propose_code_change":
        return propose_code_change(args.get("python_code", ""))
    elif tool_name == "search_memory":
        return search_memory(args.get("query", ""))
    else:
        return json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})
