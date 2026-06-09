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
from rag.database import insert_houdini_doc  # noqa: E402


def clean_wiki_text(text_str):
    """Safely cleans Houdini Wiki-text without destroying Python/VEX code."""
    # Remove carriage returns
    text_str = re.sub(r"\r\n", "\n", text_str)
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
                        embedding = core.generate_embedding(chunk)
                        insert_houdini_doc(core.db_path, title, chunk, url, embedding)

                    count += 1
                    if count % 50 == 0 or count == total_files:
                        print(
                            f"Processed [{count}/{total_files}] files from {zip_path}..."
                        )
                except Exception as e:
                    print(f"Error processing {f}: {e}")

        print(f"Finished ingesting {zip_path}. Total processed: {count}")
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

    # Idempotency Check
    try:
        with sqlite3.connect(core.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM houdini_docs")
            count = cursor.fetchone()[0]

            if count > 0 and not args.force:
                print(f"\n[ABORT] Database already populated with {count} documents.")
                print("Skipping ingestion to prevent duplicate vector charges.")
                print(
                    "If you want to rebuild it, run this script with the --force flag."
                )
                return

            if args.force:
                print(
                    f"\n[FORCE] Wiping {count} existing documents from the vector database..."
                )
                cursor.execute("DELETE FROM houdini_docs")
                cursor.execute("DELETE FROM houdini_docs_meta")
                conn.commit()
    except Exception:
        # Tables might not exist yet, which is completely fine for a fresh start
        pass

    ingest_gotchas(core)

    base_help_dir = (
        r"C:\Program Files\Side Effects Software\Houdini 21.0.440\houdini\help"
    )

    # Industry Standard: "Knowledge Base Ingestion" or "Data Ingestion Pipeline"
    # We are listing out the critical files required for the LLM to code accurately.
    critical_zips = {
        "hom": "hom.zip",  # Python API
        "nodes": "nodes.zip",  # Node Parameters & Logic
        "vex": "vex.zip",  # VEX Language
        "solaris": "solaris.zip",  # USD & LOPs
        "shade": "shade.zip",  # Shading & MaterialX
        "render": "render.zip",  # Karma & Mantra Lighting
        "commands": "commands.zip",  # HScript Commands
        "pyro": "pyro.zip",  # FX: Pyro
        "vellum": "vellum.zip",  # FX: Vellum
        "fluid": "fluid.zip",  # FX: FLIP/Fluids
        "destruction": "destruction.zip",  # FX: RBD
        "crowds": "crowds.zip",  # FX: Crowds
        "tops": "tops.zip",  # PDG / TOPs
        "character": "character.zip",  # Rigging / KineFX
    }

    # Set max_files=None to ingest the entire knowledge base
    for prefix, filename in critical_zips.items():
        zip_path = os.path.join(base_help_dir, filename)
        if os.path.exists(zip_path):
            ingest_zip(core, zip_path, prefix, max_files=None)
        else:
            print(f"Warning: Could not find {zip_path}")

    print("Ingestion complete.")


if __name__ == "__main__":
    main()
