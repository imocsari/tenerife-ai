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


# e5 models are trained asymmetrically: the question and the thing being searched are
# prefixed differently, and skipping the prefixes measurably weakens retrieval. The split
# already exists here — embed() is only ever called on a question, embed_many() only on
# documents during ingest — so the prefixes go on automatically rather than at call sites.
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


def embed(text):
    """One question -> one vector (numpy array)."""
    return _model().encode(QUERY_PREFIX + text)


def embed_many(texts, show_progress=False):
    """Many documents -> many vectors. Much faster than calling embed() in a loop."""
    return _model().encode([PASSAGE_PREFIX + t for t in texts], show_progress_bar=show_progress)


def to_pgvector(vector):
    """Format a vector the way pgvector expects: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
