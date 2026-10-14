# app/rag.py
# Orchestration only: retrieve -> build prompt -> generate.
# The details live in embeddings.py, retrievers/, prompts.py and llm.py.

from app import config, llm
from app.embeddings import embed
from app.prompts import SYSTEM_PROMPT, build_message
from app.retrievers import app_data, wikivoyage


def retrieve(question, top_k=config.TOP_K):
    """Search every knowledge source and keep the best results overall."""
    q = embed(question)
    results = wikivoyage.search(q) + app_data.search(q)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def ask(question):
    sources = retrieve(question)
    answer = llm.generate(SYSTEM_PROMPT, build_message(question, sources))
    return {
        "answer": answer,
        "sources": [
            {"type": s["type"], "title": s["title"], "url": s["url"], "score": round(s["score"], 2)}
            for s in sources
        ],
    }
