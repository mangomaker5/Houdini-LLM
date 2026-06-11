import os
import zipfile
import shutil
from bs4 import BeautifulSoup
from markdownify import markdownify as md


def process_html_to_md(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    # Doxygen's main content is usually in <div class="contents">
    content_div = soup.find("div", class_="contents")

    # If not found, try textblock or just use body
    if not content_div:
        content_div = soup.find("div", class_="textblock")
    if not content_div:
        content_div = soup.find("body")

    if not content_div:
        return ""

    # Remove unwanted Doxygen elements (like dynheader which are graphs)
    for unwanted in content_div.find_all(class_="dynheader"):
        unwanted.decompose()
    for unwanted in content_div.find_all(class_="dyncontent"):
        unwanted.decompose()

    # Flatten tables into clean readable paragraphs so we don't get ugly markdown pipes (|)
    for table in content_div.find_all("table"):
        table.name = "div"
        for tr in table.find_all("tr"):
            tr.name = "p"
            for td in tr.find_all(["td", "th"]):
                td.name = "span"
                td.append(" ")  # Add space between columns
        for tbody in table.find_all(["tbody", "thead"]):
            tbody.unwrap()

    html_to_convert = str(content_div)

    # Convert to markdown, strip=['a', 'img'] removes HTML anchors and useless Doxygen images
    markdown_text = md(html_to_convert, heading_style="ATX", strip=["a", "img"])

    # Remove ugly Doxygen specific characters
    markdown_text = markdown_text.replace("◆", "").replace("\u25c6", "")

    # Clean up excessive newlines
    lines = markdown_text.split("\n")
    cleaned_lines = []
    empty_count = 0
    for line in lines:
        if not line.strip():
            empty_count += 1
            if empty_count <= 2:
                cleaned_lines.append(line)
        else:
            empty_count = 0
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def main():
    input_dir = r"D:\dev\applications\Houdini-LLM\data\htoa-6.4.4.2-doc"
    output_zip = r"D:\dev\applications\Houdini-LLM\data\arnold.zip"

    # Create temp directory for text files
    temp_dir = os.path.join(os.path.dirname(output_zip), "temp_htoa_md")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(output_zip), exist_ok=True)

    print(f"Scanning HTML files in {input_dir}...")
    html_files = []

    # Files that contain no useful API docs, just massive tables of contents or raw source code
    skip_prefixes = (
        "dir_",
        "classes",
        "annotated",
        "hierarchy",
        "functions",
        "namespacemembers",
        "globals",
        "graph_legend",
        "inherits",
    )

    for root, _, files in os.walk(input_dir):
        if "search" in root.split(os.sep):  # Skip search index folder robustly
            continue
        for file in files:
            if file.endswith(".html"):
                # Skip raw source code files, file references (_8py, _8cpp, _8h, _8dox), and directory listings
                if (
                    file.endswith("_source.html")
                    or file.endswith("_8py.html")
                    or file.endswith("_8cpp.html")
                    or file.endswith("_8h.html")
                    or file.endswith("_8dox.html")
                    or file.startswith(skip_prefixes)
                ):
                    continue
                html_files.append(os.path.join(root, file))

    print(f"Found {len(html_files)} HTML files. Converting to Markdown...")

    processed_count = 0
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, file_path in enumerate(html_files, 1):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    html_content = f.read()

                md_text = process_html_to_md(html_content)

                if len(md_text.strip()) > 250:
                    base_name = os.path.basename(file_path).replace(".html", ".txt")
                    temp_file = os.path.join(temp_dir, base_name)

                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(md_text)

                    # Write directly to the root of the zip to match Houdini native format
                    zf.write(temp_file, base_name)
                    processed_count += 1

                print(
                    f"\rProcessed [{i}/{len(html_files)}] files...", end="", flush=True
                )

            except Exception as e:
                print(f"\nError processing {file_path}: {e}")

    print(f"\nFinished! Converted {processed_count} files.")
    print(f"Created RAG Zip: {output_zip}")

    # Cleanup temp dir
    print("Cleaning up temporary files...")
    shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
