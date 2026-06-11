import json

SEARCH_API_DOCS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_api_docs",
        "description": "Searches the Houdini API documentation (HOM and nodes) for information about classes, functions, and node parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to search the documentation for.",
                }
            },
            "required": ["query"],
        },
    },
}


def search_api_docs(query, core_ref=None):
    try:
        from rag.vector_db import search_houdini_docs

        if core_ref is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": "Internal error: core_ref not provided to search_api_docs.",
                }
            )

        embedding = core_ref.generate_embedding(query)
        results = search_houdini_docs(
            core_ref.db_path, embedding, query_text=query, limit=5
        )
        if not results:
            return json.dumps(
                {"status": "success", "message": "No related documentation found."}
            )

        return json.dumps({"status": "success", "results": results})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
