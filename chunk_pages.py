# chunk_pages.py
# Splits each downloaded page into small pieces ("chunks") and saves them all in chunks.json.

import glob
import json
import re

MAX_CHARS = 1000  # roughly one or two paragraphs per chunk

chunks = []

for path in sorted(glob.glob("data/*.json")):
    with open(path, encoding="utf-8") as f:
        page = json.load(f)
    title = page["title"]

    # Wikivoyage text uses headings like "== Get in ==" and "=== By plane ===".
    parts = re.split(r"\n=+ *(.+?) *=+\n", "\n" + page["text"])
    # parts = [intro text, heading1, text1, heading2, text2, ...]

    sections = [("Introduction", parts[0])]
    for i in range(1, len(parts), 2):
        sections.append((parts[i], parts[i + 1] if i + 1 < len(parts) else ""))

    for heading, text in sections:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if not paragraphs:
            continue  # skip empty sections (e.g. a heading with only sub-headings)

        # Group paragraphs together until we reach MAX_CHARS.
        current = ""
        for p in paragraphs:
            if current and len(current) + len(p) > MAX_CHARS:
                chunks.append({"title": title, "section": heading, "text": current})
                current = ""
            current = (current + "\n" + p).strip()
        if current:
            chunks.append({"title": title, "section": heading, "text": current})

with open("chunks.json", "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)

print(f"Created {len(chunks)} chunks")
print("Example chunk:")
print(json.dumps(chunks[min(3, len(chunks) - 1)], ensure_ascii=False, indent=2))
