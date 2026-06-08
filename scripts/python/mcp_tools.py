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
            "name": "execute_houdini_python",
            "description": "Executes python code within the Houdini session. Use this to construct nodes, set parameters, and modify the scene automatically. The execution is wrapped in an Undo block.",
            "parameters": {
                "type": "object",
                "properties": {
                    "python_code": {
                        "type": "string",
                        "description": "The valid Python hou module code to execute.",
                    }
                },
                "required": ["python_code"],
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


def execute_houdini_python(python_code):
    try:
        # Wrap the execution in an undo block so the user can hit Ctrl+Z
        with hou.undos.group("Agent Execution"):
            local_dict = {"hou": hou}
            exec(python_code, local_dict)
        return json.dumps(
            {"status": "success", "message": "Code executed successfully."}
        )
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "message": str(e),
                "details": "The executed python code threw an exception.",
            }
        )


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
    elif tool_name == "execute_houdini_python":
        return execute_houdini_python(args.get("python_code", ""))
    else:
        return json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})
