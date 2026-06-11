import json
import hou
from rag.tools import SEARCH_API_DOCS_SCHEMA, search_api_docs

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
            "name": "analyze_node_type",
            "description": "Analyzes a Houdini node type (including custom HDAs) to return its inputs, outputs, parameters, and whether it is an HDA. Use this to understand the requirements of a node before creating it.",
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

AGENT_TOOLS_SCHEMA.append(SEARCH_API_DOCS_SCHEMA)


def _extract_parms(parm_templates, output_dict):
    """Recursively extract parameter templates including inside folders."""
    for pt in parm_templates:
        if pt.type() in (hou.parmTemplateType.FolderSet, hou.parmTemplateType.Folder):
            try:
                if (
                    hasattr(pt, "folderType")
                    and pt.folderType() == hou.folderType.MultiparmBlock
                ):
                    output_dict[pt.name() + "_MULTIPARM"] = {
                        "label": pt.label(),
                        "type": "MultiparmBlock",
                        "hint": "This is a Multi-Parm block. Its child parameters use a '#' symbol in their name (e.g. 'dir#'). Replace '#' with the instance index (1-based) like 'dir1', 'dir2' after increasing this block's primary count parameter.",
                    }
                _extract_parms(pt.parmTemplates(), output_dict)
            except AttributeError:
                pass
        else:
            parm_info = {"label": pt.label(), "type": pt.type().name()}
            if hasattr(pt, "menuItems"):
                items = pt.menuItems()
                if items:
                    parm_info["menu_items"] = list(items)
                    parm_info["menu_labels"] = list(pt.menuLabels())

            if hasattr(pt, "numComponents") and pt.numComponents() > 1:
                parm_info["components"] = pt.numComponents()
                parm_info["hint"] = (
                    f"This is a Tuple with {pt.numComponents()} components. You MUST use node.parmTuple('{pt.name()}').set(...) or set individual components."
                )

            if pt.type() == hou.parmTemplateType.Ramp:
                parm_info["hint"] = (
                    f"To set this ramp, you MUST create a hou.Ramp object: ramp = hou.Ramp([hou.rampBasis.Linear, ...], [0.0, 1.0], [val1, val2]), then node.parm('{pt.name()}').set(ramp)."
                )

            if pt.type() == hou.parmTemplateType.Button:
                parm_info["hint"] = (
                    f"To trigger this button, you MUST use node.parm('{pt.name()}').pressButton(). Do not use .set()"
                )

            if pt.name() == "snippet":
                parm_info["hint"] = "This parameter expects VEX code, NOT Python."

            output_dict[pt.name()] = parm_info


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


def analyze_node_type(node_type):
    try:
        for cat in hou.nodeTypeCategories().values():
            nt = cat.nodeTypes().get(node_type)
            if nt:
                info = {
                    "status": "success",
                    "node_type": node_type,
                    "min_inputs": nt.minNumInputs(),
                    "max_inputs": nt.maxNumInputs(),
                    "is_hda": nt.definition() is not None,
                    "parameters": {},
                }
                _extract_parms(nt.parmTemplates(), info["parameters"])
                return json.dumps(info)
        return json.dumps(
            {"status": "error", "message": f"Node type '{node_type}' not found."}
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def propose_code_change(python_code):
    import ast
    import traceback

    try:
        ast.parse(python_code)
    except SyntaxError:
        err_trace = traceback.format_exc(limit=0)
        return json.dumps(
            {
                "status": "error",
                "message": f"Pre-flight Syntax Check Failed:\n{err_trace}",
                "instruction": "Fix the syntax error and propose the code again. Ensure proper indentation and valid Python.",
            }
        )

    return json.dumps(
        {
            "status": "proposed",
            "message": "Code proposed for user review.",
            "code": python_code,
        }
    )


def search_memory(query, core_ref=None):
    try:
        from memory_db import search_learned_skills, search_anti_patterns

        if core_ref is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": "Internal error: core_ref not provided to search_memory.",
                }
            )

        embedding = core_ref.generate_embedding(query)
        skills = search_learned_skills(
            core_ref.db_path, embedding, query_text=query, limit=3
        )
        anti_patterns = search_anti_patterns(
            core_ref.db_path, embedding, query_text=query, limit=2
        )

        if not skills and not anti_patterns:
            return json.dumps(
                {
                    "status": "success",
                    "message": "No related skills or anti-patterns found in memory.",
                }
            )

        return json.dumps(
            {"status": "success", "skills": skills, "anti_patterns": anti_patterns}
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def execute_tool(tool_name, arguments_json, core_ref=None):
    """Dispatches the tool call to the appropriate function."""
    try:
        args = json.loads(arguments_json)
    except json.JSONDecodeError:
        return json.dumps(
            {"status": "error", "message": "Invalid JSON arguments provided to tool."}
        )

    if tool_name == "get_node_parameters":
        return get_node_parameters(args.get("node_type", ""))
    elif tool_name == "analyze_node_type":
        return analyze_node_type(args.get("node_type", ""))
    elif tool_name == "propose_code_change":
        return propose_code_change(args.get("python_code", ""))
    elif tool_name == "search_memory":
        return search_memory(args.get("query", ""), core_ref=core_ref)
    elif tool_name == "search_api_docs":
        return search_api_docs(args.get("query", ""), core_ref=core_ref)
    else:
        return json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})
