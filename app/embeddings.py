# app/embeddings.py
# The ONLY place that knows which embedding model we use.
# Both the API and the ingest scripts import from here, so they always match.

from functools import lru_cache
from sentence_transformers import SentenceTransformer

from app import config


@lru_cache(maxsize=1)
def _model():
    # Loaded once, the first time it's needed
    return SentenceTransformer(config.EMBED_MODEL)


def embed(text):
    """One text -> one vector (numpy array)."""
    return _model().encode(text)


def embed_many(texts, show_progress=False):
    """Many texts -> many vectors. Much faster than calling embed() in a loop."""
    return _model().encode(texts, show_progress_bar=show_progress)


def to_pgvector(vector):
    """Format a vector the way pgvector expects: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
