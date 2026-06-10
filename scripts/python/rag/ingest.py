import os
import sys
import zipfile
import re
import argparse
import sqlite3
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Add the parent directory to sys.path if needed (scripts/python)
python_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(python_dir)
# Add python_libs to sys.path so sqlite_vec can be imported
sys.path.append(
    os.path.join(os.path.dirname(os.path.dirname(python_dir)), "python_libs")
)

from core import AIAgentCore  # noqa: E402
from rag.vector_db import insert_houdini_doc  # noqa: E402


def clean_wiki_text(text_str):
    """Safely cleans Houdini Wiki-text markup without destroying Python/VEX code.

    Houdini help .txt files use a custom wiki format with:
    - #type:, #cppname:, #group:, #context:, #icon: directives
    - [Hom:hou.Class#method] cross-references
    - ::`method(self)` -> return_type method signatures
    - {{{ }}} code blocks
    - @methods, @parameters, @related section markers
    - :usage: annotations
    - :include directives
    """
    # Remove carriage returns
    text_str = re.sub(r"\r\n", "\n", text_str)
    # Strip metadata directives (lines starting with #type:, #cppname:, etc.)
    text_str = re.sub(
        r"^#(type|cppname|superclass|group|context|icon|internal|since|tags|replaces|status)\b.*$",
        "",
        text_str,
        flags=re.MULTILINE,
    )
    # Convert cross-references [Hom:hou.Class#method] -> hou.Class.method
    text_str = re.sub(r"\[Hom:(hou\.[^\]#]+)#([^\]]+)\]", r"\1.\2", text_str)
    text_str = re.sub(r"\[Hom:(hou\.[^\]]+)\]", r"\1", text_str)
    # Convert VEX references [Vex:funcname] -> funcname
    text_str = re.sub(r"\[Vex:([^\]]+)\]", r"\1", text_str)
    # Convert Node references [Node:context/type] -> context/type
    text_str = re.sub(r"\[Node:([^\]]+)\]", r"\1", text_str)
    # Strip :include directives
    text_str = re.sub(r"^:include\b.*$", "", text_str, flags=re.MULTILINE)
    # Strip code block delimiters but keep content
    text_str = text_str.replace("{{{", "").replace("}}}", "")
    # Clean method definition syntax  ::`method(self)` -> method(self)
    text_str = re.sub(r"::`([^`]+)`", r"\1", text_str)
    # Strip section markers but keep as headings
    text_str = re.sub(
        r"^@(methods|parameters|related|examples)",
        r"\n== \1 ==",
        text_str,
        flags=re.MULTILINE,
    )
    # Remove excessive newlines (more than 2)
    text_str = re.sub(r"\n{3,}", "\n\n", text_str)
    return text_str.strip()


def ingest_gotchas(core):
    print("Ingesting Gotchas...")
    gotchas = [
        {
            "title": "String Expansion Gotcha",
            "content": "String Expansion: If the docs say use $F, the agent must know to pass it as a raw string r'$F' so Python doesn't try to escape it.",
            "url": "gotcha:string_expansion",
        },
        {
            "title": "Node Creation Failures Gotcha",
            "content": "Node Creation Failures: Creating nodes on invalid paths returns None, leading to NoneType errors. Always check if the path exists or if the parent node is valid.",
            "url": "gotcha:node_creation",
        },
        {
            "title": "ParmTemplateGroup Modification Gotcha",
            "content": "ParmTemplateGroup Modification: The agent cannot simply use addParmTuple(). It must extract the group via parmTemplateGroup(), append the template, and set it back via setParmTemplateGroup().",
            "url": "gotcha:parm_template_group",
        },
    ]
    for g in gotchas:
        try:
            embedding = core.generate_embedding(g["content"])
            insert_houdini_doc(
                core.db_path, g["title"], g["content"], g["url"], embedding
            )
            print(f"Ingested Gotcha: {g['title']}")
        except Exception as e:
            print(f"Error ingesting gotcha: {e}")
    print("Gotchas ingested.")


def ingest_zip(core, zip_path, prefix, max_files=None):
    if not os.path.exists(zip_path):
        print(f"Warning: {zip_path} not found. Skipping.")
        return

    print(f"Ingesting {zip_path}...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Houdini Help files are actually .txt Wiki-text files, NOT HTML!
            txt_files = [f for f in zf.namelist() if f.endswith(".txt")]
            if not txt_files:
                print(f"No .txt files found in {zip_path}")
                return

            total_files = len(txt_files)
            print(f"Found {total_files} .txt files in {zip_path}")
            count = 0

            for f in txt_files:
                if max_files and count >= max_files:
                    total_files = max_files
                    break
                try:
                    content_bytes = zf.read(f)
                    content_str = content_bytes.decode("utf-8", errors="ignore")
                    clean_text = clean_wiki_text(content_str)

                    if len(clean_text) < 50:
                        continue

                    # Proper Industry Standard Recursive Chunking using LangChain
                    text_splitter = RecursiveCharacterTextSplitter(
                        chunk_size=1500,
                        chunk_overlap=200,
                        separators=["\n\n", "\n", " ", ""],
                    )
                    chunks = text_splitter.split_text(clean_text)

                    title = f.split("/")[-1]
                    url = f"{prefix}/{f}"

                    for chunk in chunks:
                        # Context Injection: Prepend the node title to the chunk
                        enriched_chunk = f"[{prefix}/{title}] {chunk}"
                        embedding = core.generate_embedding(enriched_chunk)
                        insert_houdini_doc(
                            core.db_path, title, enriched_chunk, url, embedding
                        )

                    count += 1
                    print(
                        f"\rProcessed [{count}/{total_files}] files from {prefix}...",
                        end="",
                        flush=True,
                    )
                except Exception as e:
                    print(f"\nCritical error processing {f}: {e}")
                    print(f"Aborting current zip ingestion ({prefix}) due to error.")
                    return  # Break completely so we don't leak memory or falsely mark ingested

        print(f"\nFinished ingesting {zip_path}. Total processed: {count}")
        from rag.vector_db import mark_zip_ingested

        mark_zip_ingested(core.db_path, prefix)
    except Exception as e:
        print(f"Error opening zip file {zip_path}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Houdini-LLM RAG Ingestion Pipeline")
    parser.add_argument(
        "--force", action="store_true", help="Force wipe and rebuild of the database."
    )
    args = parser.parse_args()

    print("Initializing Core...")
    core = AIAgentCore()
    if not core.api_key:
        print(
            "Error: Please set your OpenRouter API key. Cannot generate embeddings without it."
        )
        return

    # Force Wipe
    if args.force:
        try:
            with sqlite3.connect(core.db_path) as conn:
                cursor = conn.cursor()
                print("\n[FORCE] Wiping existing documents from the vector database...")
                for tbl in [
                    "houdini_docs",
                    "houdini_docs_meta",
                    "houdini_docs_fts",
                    "houdini_ingest_status",
                ]:
                    try:
                        cursor.execute(f"DELETE FROM {tbl}")
                    except Exception:
                        pass
                conn.commit()
        except Exception:
            pass

    # Ingest gotchas only if they don't exist
    try:
        with sqlite3.connect(core.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM houdini_docs_meta WHERE url LIKE 'gotcha:%'"
            )
            if c.fetchone()[0] == 0:
                ingest_gotchas(core)
    except Exception:
        pass

    base_help_dir = (
        r"C:\Program Files\Side Effects Software\Houdini 21.0.440\houdini\help"
    )

    critical_zips = {
        "hom": "hom.zip",
        "nodes": "nodes.zip",
        "vex": "vex.zip",
        "solaris": "solaris.zip",
        "shade": "shade.zip",
        "render": "render.zip",
        "commands": "commands.zip",
        "pyro": "pyro.zip",
        "vellum": "vellum.zip",
        "fluid": "fluid.zip",
        "destruction": "destruction.zip",
        "crowds": "crowds.zip",
        "tops": "tops.zip",
        "character": "character.zip",
    }

    from rag.vector_db import delete_houdini_docs_by_prefix

    while True:
        print("\n=========================================")
        print("    Houdini-LLM RAG Ingestion Menu")
        print("=========================================")

        status_map = {}
        try:
            with sqlite3.connect(core.db_path) as conn:
                c = conn.cursor()
                c.execute(
                    "CREATE TABLE IF NOT EXISTS houdini_ingest_status (prefix TEXT PRIMARY KEY, status TEXT)"
                )
                for prefix in critical_zips.keys():
                    c.execute(
                        "SELECT status FROM houdini_ingest_status WHERE prefix = ?",
                        (prefix,),
                    )
                    row = c.fetchone()
                    if row and row[0] == "completed":
                        status_map[prefix] = "✅ Ingested"
                    else:
                        c.execute(
                            "SELECT COUNT(*) FROM houdini_docs_meta WHERE url LIKE ?",
                            (f"{prefix}/%",),
                        )
                        count = c.fetchone()[0]
                        status_map[prefix] = "⚠️ Partial" if count > 0 else "⏳ Pending"
        except Exception:
            for prefix in critical_zips.keys():
                status_map[prefix] = "⏳ Pending"

        zip_keys = list(critical_zips.keys())
        for i, prefix in enumerate(zip_keys, 1):
            print(f" [{i:2d}] {prefix:<15s} (Status: {status_map[prefix]})")

        print(" -----------------------------------------")
        print(" [F]  Force Rebuild ENTIRE Database")
        print(" [Q]  Quit")
        print("=========================================")

        choice = input("Select an option: ").strip().upper()

        if choice == "Q":
            print("Exiting.")
            break

        elif choice == "F":
            ans = (
                input(
                    "WARNING: This will delete ALL vectors and rebuild. Are you sure? (y/n): "
                )
                .strip()
                .lower()
            )
            if ans == "y":
                try:
                    with sqlite3.connect(core.db_path) as conn:
                        cursor = conn.cursor()
                        print(
                            "\n[FORCE] Wiping existing documents from the vector database..."
                        )
                        for tbl in [
                            "houdini_docs",
                            "houdini_docs_meta",
                            "houdini_docs_fts",
                            "houdini_ingest_status",
                        ]:
                            try:
                                cursor.execute(f"DELETE FROM {tbl}")
                            except Exception:
                                pass
                        conn.commit()
                except Exception:
                    pass
                for prefix in zip_keys:
                    zip_path = os.path.join(base_help_dir, critical_zips[prefix])
                    if os.path.exists(zip_path):
                        ingest_zip(core, zip_path, prefix, max_files=None)
                print("\nForce rebuild completed.")

        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(zip_keys):
                prefix = zip_keys[idx]
                if status_map[prefix] == "✅ Ingested":
                    ans = (
                        input(
                            f"This zip ({prefix}) is already ingested. Do you want to overwrite it? (y/n): "
                        )
                        .strip()
                        .lower()
                    )
                    if ans == "y":
                        print(f"Deleting existing vectors for {prefix}...")
                        delete_houdini_docs_by_prefix(core.db_path, prefix)
                        zip_path = os.path.join(base_help_dir, critical_zips[prefix])
                        if os.path.exists(zip_path):
                            ingest_zip(core, zip_path, prefix, max_files=None)
                elif status_map[prefix] == "⚠️ Partial":
                    ans = (
                        input(
                            f"This zip ({prefix}) is partially ingested. Do you want to restart it? (y/n): "
                        )
                        .strip()
                        .lower()
                    )
                    if ans == "y":
                        print(f"Cleaning up partial ingestion for {prefix}...")
                        delete_houdini_docs_by_prefix(core.db_path, prefix)
                        zip_path = os.path.join(base_help_dir, critical_zips[prefix])
                        if os.path.exists(zip_path):
                            ingest_zip(core, zip_path, prefix, max_files=None)
                else:
                    zip_path = os.path.join(base_help_dir, critical_zips[prefix])
                    if os.path.exists(zip_path):
                        ingest_zip(core, zip_path, prefix, max_files=None)
                    else:
                        print(f"Warning: Could not find {zip_path}")
            else:
                print("Invalid number selection.")
        else:
            print("Invalid input.")


if __name__ == "__main__":
    main()
