# embed_chunks.py
# Creates embeddings on your own computer with a free open-source model.

import json
from sentence_transformers import SentenceTransformer

# Downloads the model the first time (~90 MB), then works offline.
model = SentenceTransformer("BAAI/bge-small-en-v1.5")

with open("chunks.json", encoding="utf-8") as f:
    chunks = json.load(f)

texts = [f"{c['title']} – {c['section']}\n{c['text']}" for c in chunks]

embeddings = model.encode(texts, show_progress_bar=True)

for chunk, emb in zip(chunks, embeddings):
    chunk["embedding"] = emb.tolist()

with open("chunks_with_embeddings.json", "w", encoding="utf-8") as f:
    json.dump(chunks, f)

print("Done. Each embedding has", len(chunks[0]["embedding"]), "numbers.")
