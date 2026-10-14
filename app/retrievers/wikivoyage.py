# app/retrievers/wikivoyage.py
# Searches the Wikivoyage chunks stored in data/chunks_with_embeddings.json.

import json
from functools import lru_cache

import numpy as np

from app import config


@lru_cache(maxsize=1)
def _load():
    """Load chunks once and stack their vectors into one matrix for fast search."""
    if not config.EMBEDDED_CHUNKS_FILE.exists():
        return [], None
    with open(config.EMBEDDED_CHUNKS_FILE, encoding="utf-8") as f:
        chunks = json.load(f)
    matrix = np.array([c["embedding"] for c in chunks], dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)   # normalise once
    return chunks, matrix


def search(query_vector, top_k=5):
    chunks, matrix = _load()
    if not chunks:
        return []

    q = np.asarray(query_vector, dtype=np.float32)
    q /= np.linalg.norm(q)
    scores = matrix @ q                       # cosine similarity with every chunk at once
    best = np.argsort(scores)[::-1][:top_k]

    return [{
        "type": "guide",
        "title": f"{chunks[i]['title']} – {chunks[i]['section']}",
        "content": chunks[i]["text"],
        "url": None,
        "score": float(scores[i]),
    } for i in best]
