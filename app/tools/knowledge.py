# app/tools/knowledge.py
# Retrieval as a tool, so the model decides when your own data is the right source.
#
# Before this, every question ran a vector search whether or not it needed one — "what's the
# weather in Los Gigantes" searched 1,900 events to find nothing useful. As a tool it is just
# one option among several, and the model can also use it twice in one answer (events AND
# venues) when a question needs that.

from contextvars import ContextVar

# What the last search returned, so the API can still report its sources. A ContextVar rather
# than a plain list so concurrent requests under uvicorn cannot read each other's sources.
LAST_SOURCES = ContextVar("last_sources", default=None)


def search_tenerinfo(query, top_k=6):
    """Search TenerInfo's own events, venues and tours, plus a Tenerife travel guide."""
    from app import rag   # imported here: rag imports this module, so top-level would cycle

    found = rag.retrieve(query, top_k=int(top_k))
    collected = LAST_SOURCES.get()
    if collected is None:
        collected = []
        LAST_SOURCES.set(collected)
    collected.extend(found)

    if not found:
        return "Nothing in TenerInfo's data matched that."
    return "\n\n".join(
        f"[{i}] ({s['type']}) {s['title']}\n{s['content']}"
        for i, s in enumerate(found, start=1)
    )


TOOLS = {
    "search_tenerinfo": {
        "description": (
            "Search TenerInfo's own data — events happening in Tenerife, venues (bars, "
            "restaurants, clubs), tours — and a Tenerife travel guide. Use this for anything "
            "about what is on, where to go, or what a place is like. Search again with "
            "different wording if the first results are not useful."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for, in natural language"},
                "top_k": {"type": "integer", "description": "How many results to return (default 6)"},
            },
            "required": ["query"],
        },
        "run": search_tenerinfo,
    },
}
