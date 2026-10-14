# app/rag.py
# Orchestration only: retrieve -> build prompt -> generate.
# The details live in embeddings.py, retrievers/, prompts.py and llm.py.

from app import config, llm
from app.embeddings import embed
from app.prompts import SYSTEM_PROMPT, TOOL_SYSTEM_PROMPT, build_message
from app.retrievers import app_data, wikivoyage


def retrieve(question, top_k=config.TOP_K):
    """Search every knowledge source and keep the best results overall."""
    q = embed(question)
    results = wikivoyage.search(q) + app_data.search(q)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def ask(question):
    """Answer a question, letting the model choose its own sources.

    Retrieval used to run unconditionally before every answer; now it is one tool among
    several (app/tools/), so a weather question no longer searches 1,900 events first, and a
    question needing both — "what's on tonight, and will it rain?" — can use both. Sources are
    whatever the model actually looked at, collected as the search tool runs.
    """
    from app.tools import knowledge

    knowledge.LAST_SOURCES.set([])
    answer = llm.generate_with_tools(TOOL_SYSTEM_PROMPT, question)

    # The model may search several times; show each source once, at its best score.
    best = {}
    for s in knowledge.LAST_SOURCES.get() or []:
        key = (s["type"], s["title"])
        if key not in best or s["score"] > best[key]["score"]:
            best[key] = s

    return {
        "answer": answer,
        "sources": [
            {"type": s["type"], "title": s["title"], "url": s["url"], "score": round(s["score"], 2)}
            for s in sorted(best.values(), key=lambda s: s["score"], reverse=True)
        ],
    }
