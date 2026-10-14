# app/prompts.py
# Everything about WHAT we say to the model.

SYSTEM_PROMPT = (
    "You are a helpful Tenerife travel assistant. "
    "Answer ONLY using the sources provided. "
    "If the sources don't contain the answer, say you don't know. "
    "Mention which source(s) you used, e.g. (Source 2). "
    "When you mention an event, include its date and time."
)


def build_message(question, sources):
    """Put the numbered sources and the question into one message."""
    context = "\n\n".join(
        f"[Source {i}: {s['type']} – {s['title']}]\n{s['content']}"
        for i, s in enumerate(sources, start=1)
    )
    return f"Sources:\n{context}\n\nQuestion: {question}"
