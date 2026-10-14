# tests/test_rag.py
# Run from the project folder with:  pytest
# These tests replace the slow/external parts with fakes, so they don't need
# Ollama, Claude, Supabase or the embedding model.

from ingest.chunk_pages import chunk_page
from app import rag
from app.prompts import build_message


def source(title, score, type_="guide"):
    return {"type": type_, "title": title, "content": f"About {title}", "url": None, "score": score}


def test_chunk_page_splits_on_headings():
    text = "Intro text.\n\n== Get in ==\n\n=== By boat ===\nFerries to La Gomera.\n"
    chunks = chunk_page("Los Cristianos", text)

    assert [c["section"] for c in chunks] == ["Introduction", "By boat"]
    assert chunks[1]["text"] == "Ferries to La Gomera."


def test_build_message_numbers_the_sources():
    message = build_message("Where to swim?", [source("Beach", 0.9), source("Harbour", 0.5)])

    assert "[Source 1: guide – Beach]" in message
    assert "[Source 2: guide – Harbour]" in message
    assert message.endswith("Question: Where to swim?")


def test_retrieve_merges_sources_by_score(monkeypatch):
    monkeypatch.setattr(rag, "embed", lambda text: [0.0])
    monkeypatch.setattr(rag.wikivoyage, "search", lambda q: [source("Guide", 0.4)])
    monkeypatch.setattr(rag.app_data, "search", lambda q: [source("Jazz Night", 0.8, "event")])

    results = rag.retrieve("live music?")

    assert [r["title"] for r in results] == ["Jazz Night", "Guide"]


def test_ask_returns_answer_and_sources(monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda q: [source("Beach", 0.9)])
    monkeypatch.setattr(rag.llm, "generate", lambda system, message: "Try Playa de las Vistas (Source 1).")

    result = rag.ask("Where to swim?")

    assert result["answer"] == "Try Playa de las Vistas (Source 1)."
    assert result["sources"] == [{"type": "guide", "title": "Beach", "url": None, "score": 0.9}]
