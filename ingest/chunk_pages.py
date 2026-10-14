# ingest/chunk_pages.py
# Splits each downloaded page into section-aware chunks -> data/chunks.json
# Run from the project folder:  python -m ingest.chunk_pages

import json
import re

from app import config

MAX_CHARS = 1000


def split_sections(text):
    """'== Get in ==' style headings -> [(heading, text), ...]"""
    parts = re.split(r"\n=+ *(.+?) *=+\n", "\n" + text)
    sections = [("Introduction", parts[0])]
    for i in range(1, len(parts), 2):
        sections.append((parts[i], parts[i + 1] if i + 1 < len(parts) else ""))
    return sections


def chunk_page(title, text, max_chars=MAX_CHARS):
    chunks = []
    for heading, body in split_sections(text):
        paragraphs = [p.strip() for p in body.split("\n") if p.strip()]
        current = ""
        for p in paragraphs:
            if current and len(current) + len(p) > max_chars:
                chunks.append({"title": title, "section": heading, "text": current})
                current = ""
            current = (current + "\n" + p).strip()
        if current:
            chunks.append({"title": title, "section": heading, "text": current})
    return chunks


def main():
    chunks = []
    for path in sorted(config.PAGES_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            page = json.load(f)
        chunks += chunk_page(page["title"], page["text"])

    with open(config.CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"Created {len(chunks)} chunks")


if __name__ == "__main__":
    main()
