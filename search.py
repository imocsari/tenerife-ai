# search.py
import json
import sys
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")   # must be the SAME model as embed_chunks.py

with open("chunks_with_embeddings.json", encoding="utf-8") as f:
    chunks = json.load(f)

question = sys.argv[1]
q = model.encode(question)

scores = []
for c in chunks:
    e = np.array(c["embedding"])
    score = np.dot(q, e) / (np.linalg.norm(q) * np.linalg.norm(e))
    scores.append((score, c))

scores.sort(key=lambda x: x[0], reverse=True)
for score, c in scores[:3]:
    print(f"\n[{score:.2f}] {c['title']} – {c['section']}")
    print(c["text"][:300], "...")
