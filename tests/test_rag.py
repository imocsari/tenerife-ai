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

    def fake_model(system, question, history=None):
        knowledge.search_tenerinfo("where to swim")      # the model reaching for the tool
        return "Try Playa de las Vistas."

    monkeypatch.setattr(rag.llm, "generate_with_tools", fake_model)

    result = rag.ask("Where to swim?")

    assert result["answer"] == "Try Playa de las Vistas."
    assert result["sources"] == [{"type": "guide", "title": "Beach", "url": None, "score": 0.9}]


def test_ask_reports_no_sources_when_no_search_happened(monkeypatch):
    """A weather-only question searches nothing, and must not claim sources it never read."""
    monkeypatch.setattr(rag.llm, "generate_with_tools",
                        lambda s, q, h=None: "It is 24C and overcast.")

    assert rag.ask("Weather in Los Gigantes?")["sources"] == []


def test_ask_deduplicates_a_source_found_by_two_searches(monkeypatch):
    """The model often searches twice with different wording; the same venue must appear once,
    at its best score, rather than twice in the source list."""
    from app.tools import knowledge

    scores = iter([0.6, 0.9])
    monkeypatch.setattr(rag, "retrieve", lambda q, top_k=6: [source("Beach", next(scores))])

    def fake_model(system, question, history=None):
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


# --- TITSA buses -----------------------------------------------------------------------
# The after-midnight rules are the easy thing to get wrong and the hard thing to notice:
# a bug here silently hides the last buses of the night rather than raising anything.

def test_after_midnight_times_display_as_real_clock_times():
    """GTFS writes a 00:40 bus as 24:40. Showing that to a user would be nonsense."""
    from app.tools.buses import _fmt

    assert _fmt(24 * 3600 + 40 * 60, "24:40:00") == "00:40 (after midnight)"
    assert _fmt(23 * 3600 + 15 * 60, "23:15:00") == "23:15"


def test_small_hours_still_count_as_last_nights_service_day(monkeypatch):
    """At 01:30 the buses still running are yesterday's service, listed at 25:30. Treating it
    as a new day would report 'no more buses' while they were still running."""
    import datetime as real_datetime
    from app.tools import buses

    class FakeDateTime(real_datetime.datetime):
        @classmethod
        def now(cls):
            return cls(2026, 10, 15, 1, 30)

    monkeypatch.setattr(buses, "datetime", FakeDateTime)

    seconds, service_date = buses._now_seconds_and_date()

    assert seconds == 25 * 3600 + 30 * 60          # offset past 24:00, not 1.5h
    assert service_date == real_datetime.date(2026, 10, 14)   # yesterday's service day


def test_daytime_uses_today_and_plain_seconds(monkeypatch):
    import datetime as real_datetime
    from app.tools import buses

    class FakeDateTime(real_datetime.datetime):
        @classmethod
        def now(cls):
            return cls(2026, 10, 15, 14, 5)

    monkeypatch.setattr(buses, "datetime", FakeDateTime)

    seconds, service_date = buses._now_seconds_and_date()

    assert seconds == 14 * 3600 + 5 * 60
    assert service_date == real_datetime.date(2026, 10, 15)


def test_gtfs_times_past_midnight_parse_rather_than_fail():
    """33,623 rows in the real feed are at hour 24-30; a time parser would reject them."""
    from ingest.sync_titsa import seconds

    assert seconds("25:30:00") == 91800
    assert seconds("30:00:00") == 108000
    assert seconds("") is None


# --- moon phase ------------------------------------------------------------------------
# Arithmetic rather than an API call, so it is worth asserting it actually tracks the moon.

def test_moon_phase_tracks_the_lunar_cycle():
    from datetime import datetime, timezone
    from app.tools.stargazing import moon_phase

    new_fraction, new_name = moon_phase(datetime(2026, 10, 11, tzinfo=timezone.utc))
    full_fraction, full_name = moon_phase(datetime(2026, 10, 26, tzinfo=timezone.utc))

    assert new_name == "new moon" and new_fraction < 0.05
    assert full_name == "full moon" and full_fraction > 0.95


def test_moon_phase_is_cyclic():
    """A synodic month later, the moon is where it started — catches drift in the arithmetic."""
    from datetime import datetime, timedelta, timezone
    from app.tools.stargazing import moon_phase

    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    a, _ = moon_phase(start)
    b, _ = moon_phase(start + timedelta(days=29.530588853))

    assert abs(a - b) < 0.01


# --- conversation memory ---------------------------------------------------------------
# A follow-up like "near Los Cristianos" is meaningless without the question before it.

def test_history_is_passed_to_the_model(monkeypatch):
    seen = {}

    def fake(system, question, history=None):
        seen["question"], seen["history"] = question, history
        return "ok"

    monkeypatch.setattr(rag.llm, "generate_with_tools", fake)
    rag.ask("near los cristianos",
            [{"role": "user", "content": "where can I watch football tonight?"},
             {"role": "assistant", "content": "At Scallywags in Costa Adeje."}])

    assert seen["question"] == "near los cristianos"
    assert [h["role"] for h in seen["history"]] == ["user", "assistant"]


def test_history_keeps_only_clean_recent_turns():
    """Tool calls and blanks are dropped, and the window is capped — replaying tool results
    would be large, redundant, and would nudge the model to repeat calls it already made."""
    from app.llm import _as_turns, MAX_HISTORY_TURNS

    messy = ([{"role": "user", "content": "a"}, {"role": "tool", "content": "huge tool output"},
              {"role": "assistant", "content": ""}] * 10)
    turns = _as_turns(messy)

    assert len(turns) <= MAX_HISTORY_TURNS
    assert all(t["role"] in ("user", "assistant") and t["content"].strip() for t in turns)


def test_no_history_still_works():
    from app.llm import _as_turns
    assert _as_turns(None) == [] and _as_turns([]) == []
