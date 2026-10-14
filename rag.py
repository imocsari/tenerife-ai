# rag.py
# The RAG "service object": retrieval + generation, no web code here.

import json
import os
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama") 

embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")

with open("chunks_with_embeddings.json", encoding="utf-8") as f:
    CHUNKS = json.load(f)

SYSTEM_PROMPT = (
    "You are a helpful Tenerife travel assistant. "
    "Answer ONLY using the sources provided. "
    "If the sources don't contain the answer, say you don't know. "
    "Mention which source(s) you used, e.g. (Source 2)."
)


def find_chunks(question, top_k=5):
    q = embedder.encode(question)
    scored = []
    for c in CHUNKS:
        e = np.array(c["embedding"])
        score = float(np.dot(q, e) / (np.linalg.norm(q) * np.linalg.norm(e)))
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def generate(question, context):
    user_message = f"Sources:\n{context}\n\nQuestion: {question}"

    if LLM_PROVIDER == "claude":
        from anthropic import Anthropic
        response = Anthropic().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    import ollama
    response = ollama.chat(
        model="llama3.2",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return response["message"]["content"]


def ask(question):
    found = find_chunks(question)
    context = "\n\n".join(
        f"[Source {i+1}: {c['title']} – {c['section']}]\n{c['text']}"
        for i, (score, c) in enumerate(found)
    )
    answer = generate(question, context)
    return {
        "answer": answer,
        "sources": [
            {"title": c["title"], "section": c["section"], "score": round(score, 2)}
            for score, c in found
        ],
    }
