# ingest/embed_chunks.py
# Adds an embedding to every chunk -> data/chunks_with_embeddings.json
# Run from the project folder:  python -m ingest.embed_chunks

import json

from app import config
from app.embeddings import embed_many


def main():
    with open(config.CHUNKS_FILE, encoding="utf-8") as f:
        chunks = json.load(f)

    texts = [f"{c['title']} – {c['section']}\n{c['text']}" for c in chunks]
    for chunk, vector in zip(chunks, embed_many(texts, show_progress=True)):
        chunk["embedding"] = vector.tolist()

    with open(config.EMBEDDED_CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f)
    print(f"Done. {len(chunks)} chunks, {len(chunks[0]['embedding'])} numbers each.")


if __name__ == "__main__":
    main()
