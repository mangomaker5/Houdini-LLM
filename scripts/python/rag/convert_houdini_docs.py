import os
import zipfile
import re


def clean_wiki_text(text_str):
    """Safely cleans Houdini Wiki-text markup into Markdown without destroying code."""
    # Remove carriage returns
    text_str = re.sub(r"\r\n", "\n", text_str)

    # Strip metadata directives
    text_str = re.sub(
        r"^#(type|cppname|superclass|group|context|icon|internal|since|tags|replaces|status|namespace|bestbet|query|subtopics_title|sortedby)\b.*$",
        "",
        text_str,
        flags=re.MULTILINE | re.IGNORECASE,
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

    # Clean method definition syntax  ::`method(self)` -> method(self)
    text_str = re.sub(r"::`([^`]+)`", r"\1", text_str)

    # Convert Houdini parameter definitions `::value:` to Markdown `**value**:`
    text_str = re.sub(r"^::\s*([^:]+):\s*", r"\n**\1**: ", text_str, flags=re.MULTILINE)

    # Convert Houdini Headers `= Title =` and `== Subtitle ==`
    text_str = re.sub(r"^==\s*(.+?)\s*==\s*$", r"## \1", text_str, flags=re.MULTILINE)
    text_str = re.sub(r"^=\s*(.+?)\s*=\s*$", r"# \1", text_str, flags=re.MULTILINE)

    # Strip section markers but keep as headings (e.g. @methods -> ## methods)
    text_str = re.sub(
        r"^@(methods|parameters|related|examples|subtopics|inputs|outputs)",
        r"\n## \1",
        text_str,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # Convert code block delimiters {{{ and }}} to Markdown ```
    text_str = text_str.replace("{{{", "```\n").replace("}}}", "\n```")

    # Clean up excessive newlines
    # Trim trailing whitespace
    text_str = re.sub(r"[ \t]+$", "", text_str, flags=re.MULTILINE)
    # Collapse 3 or more consecutive newlines into exactly 2
    text_str = re.sub(r"\n{3,}", "\n\n", text_str)

    return text_str.strip()


def main():
    base_help_dir = (
        r"C:\Program Files\Side Effects Software\Houdini 21.0.440\houdini\help"
    )
    output_dir = r"D:\dev\applications\Houdini-LLM\data\houdini"
    os.makedirs(output_dir, exist_ok=True)

    zips_to_process = [
        "hom.zip",
        "nodes.zip",
        "vex.zip",
        "solaris.zip",
        "shade.zip",
        "render.zip",
        "basics.zip",
        "network.zip",
        "model.zip",
        "copy.zip",
        "assets.zip",
    ]

    for zip_name in zips_to_process:
        input_zip = os.path.join(base_help_dir, zip_name)
        if not os.path.exists(input_zip):
            print(f"Skipping {zip_name}, not found in {base_help_dir}")
            continue

        output_zip = os.path.join(output_dir, zip_name)
        print(f"\nProcessing {zip_name} -> {output_zip}")

        processed_count = 0
        skipped_count = 0

        try:
            with (
                zipfile.ZipFile(input_zip, "r") as in_z,
                zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as out_z,
            ):
                for file_info in in_z.infolist():
                    file_path = file_info.filename

                    # Skip index files and non-txt files
                    if file_path.endswith("index.txt"):
                        skipped_count += 1
                        continue
                    if not file_path.endswith(".txt"):
                        continue

                    content_bytes = in_z.read(file_path)
                    content_str = content_bytes.decode("utf-8", errors="ignore")

                    clean_text = clean_wiki_text(content_str)

                    if len(clean_text) > 50:
                        out_z.writestr(file_path, clean_text)
                        processed_count += 1

            print(
                f"Finished {zip_name}: Processed {processed_count} files, Skipped {skipped_count} index files."
            )
        except Exception as e:
            print(f"Error processing {zip_name}: {e}")


if __name__ == "__main__":
    main()
