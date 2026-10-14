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


def test_ask_reports_the_sources_the_search_tool_actually_used(monkeypatch):
    """ask() no longer retrieves up front — the model does, by calling search_tenerinfo.
    So the fake stands in for the model, and calls the tool the way the model would."""
    from app.tools import knowledge

    monkeypatch.setattr(rag, "retrieve", lambda q, top_k=6: [source("Beach", 0.9)])

    def fake_model(system, question):
        knowledge.search_tenerinfo("where to swim")      # the model reaching for the tool
        return "Try Playa de las Vistas."

    monkeypatch.setattr(rag.llm, "generate_with_tools", fake_model)

    result = rag.ask("Where to swim?")

    assert result["answer"] == "Try Playa de las Vistas."
    assert result["sources"] == [{"type": "guide", "title": "Beach", "url": None, "score": 0.9}]


def test_ask_reports_no_sources_when_no_search_happened(monkeypatch):
    """A weather-only question searches nothing, and must not claim sources it never read."""
    monkeypatch.setattr(rag.llm, "generate_with_tools", lambda s, q: "It is 24C and overcast.")

    assert rag.ask("Weather in Los Gigantes?")["sources"] == []


def test_ask_deduplicates_a_source_found_by_two_searches(monkeypatch):
    """The model often searches twice with different wording; the same venue must appear once,
    at its best score, rather than twice in the source list."""
    from app.tools import knowledge

    scores = iter([0.6, 0.9])
    monkeypatch.setattr(rag, "retrieve", lambda q, top_k=6: [source("Beach", next(scores))])

    def fake_model(system, question):
        knowledge.search_tenerinfo("swim")
        knowledge.search_tenerinfo("beach")
        return "Playa de las Vistas."

    monkeypatch.setattr(rag.llm, "generate_with_tools", fake_model)

    assert rag.ask("Where to swim?")["sources"] == [
        {"type": "guide", "title": "Beach", "url": None, "score": 0.9}
    ]


def test_tool_failures_come_back_as_text_not_exceptions():
    """A broken tool must return something the model can read and recover from — if it raised,
    one failing API would take down the whole answer."""
    from app import tools

    assert "No such tool" in tools.run("no_such_tool", {})
    assert "Wrong arguments" in tools.run("get_weather", {"nonsense": 1})


def test_every_tool_is_offered_to_both_providers():
    """The schemas are written once and translated; a tool missing from one provider's list
    would silently work on Claude and not on Ollama."""
    from app import tools

    claude = {t["name"] for t in tools.anthropic_schemas()}
    ollama = {t["function"]["name"] for t in tools.ollama_schemas()}

    assert claude == ollama == set(tools.REGISTRY)
