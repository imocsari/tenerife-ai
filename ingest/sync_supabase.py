# ingest/sync_supabase.py
# Run from the project folder:  python -m ingest.sync_supabase
#
# Reads active events, places (venues) and tours from your Supabase database,
# turns each one into a readable text "document", creates an embedding for it,
# and saves everything in ONE new table: ai_documents.
#
# Your app's own tables are only READ, never changed.
# Run it again whenever you want to refresh the AI's knowledge (e.g. every night).

from datetime import date

import psycopg
from psycopg.rows import dict_row

from app import config
from app.embeddings import embed_many, to_pgvector

# ---------------------------------------------------------------------------
# 1. The new table (created once; safe to run again)
# ---------------------------------------------------------------------------
SETUP_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ai_documents (
    id            bigserial PRIMARY KEY,
    source_type   text NOT NULL,          -- 'event', 'place' or 'tour'
    source_id     uuid NOT NULL,          -- id of the row in your app's table
    title         text NOT NULL,
    content       text NOT NULL,          -- the text the AI reads
    area          text,                   -- town / area, for filtering
    event_date    date,                   -- only for events
    is_recurring  boolean DEFAULT false,  -- only for events
    url           text,
    embedding     vector({config.EMBED_DIM}) NOT NULL,
    updated_at    timestamptz DEFAULT now(),
    UNIQUE (source_type, source_id)
);

-- Fast similarity search
CREATE INDEX IF NOT EXISTS ai_documents_embedding_idx
    ON ai_documents USING hnsw (embedding vector_cosine_ops);

-- IMPORTANT for Supabase: tables in "public" are reachable through the public API.
-- Turning on Row Level Security with no policies blocks that API access.
-- Your Python scripts connect as the database owner, so they still work.
ALTER TABLE ai_documents ENABLE ROW LEVEL SECURITY;
"""

# ---------------------------------------------------------------------------
# 2. Read your app's data
# ---------------------------------------------------------------------------
EVENTS_SQL = """
SELECT e.id, e.name, e.description, e.date, e.start_time, e.end_time,
       e.category, e.tags, e.is_free, e.price, e.currency, e.ticket_url,
       e.recurrence_days, e.address AS event_address,
       p.name AS place_name, p.area, p.address AS place_address,
       (SELECT string_agg(a.name, ', ' ORDER BY ea.sort_order)
          FROM event_artists ea JOIN artists a ON a.id = ea.artist_id
         WHERE ea.event_id = e.id) AS artists
FROM events e
LEFT JOIN places p ON p.id = e.place_id
WHERE e.is_active IS TRUE
  AND COALESCE(e.pending_review, false) = false
  AND (e.date >= CURRENT_DATE
       OR COALESCE(array_length(e.recurrence_days, 1), 0) > 0)
"""

PLACES_SQL = """
SELECT id, name, description, address, area, category, cuisines, tags,
       price_range, opening_hours, website, languages
FROM places
WHERE is_active IS TRUE
  AND COALESCE(pending_review, false) = false
"""

TOURS_SQL = """
SELECT id, name, description, category, duration, departure_times,
       meeting_point, languages, included, price, currency, booking_url
FROM tours
WHERE is_active IS TRUE
  AND COALESCE(pending_review, false) = false
"""


# ---------------------------------------------------------------------------
# 3. Turn rows into readable text
# ---------------------------------------------------------------------------
def join(values):
    """['a', 'b'] -> 'a, b'  (handles None and empty lists)"""
    return ", ".join(str(v) for v in values) if values else ""


def price_text(is_free, price, currency):
    if is_free:
        return "Free"
    if price is not None:
        return f"{price} {currency or 'EUR'}"
    return ""


def event_to_text(r):
    lines = [f"Event: {r['name']}"]
    where = ", ".join(x for x in [r["place_name"], r["area"]] if x)
    if where:
        lines.append(f"Where: {where}")
    address = r["place_address"] or r["event_address"]
    if address:
        lines.append(f"Address: {address}")
    if r["recurrence_days"]:
        lines.append(f"When: every {join(r['recurrence_days'])}")
    elif r["date"]:
        lines.append(f"When: {r['date'].strftime('%A %d %B %Y')}")
    times = " – ".join(t for t in [r["start_time"], r["end_time"]] if t)
    if times:
        lines.append(f"Time: {times}")
    if r["artists"]:
        lines.append(f"Artists: {r['artists']}")
    if r["category"]:
        lines.append(f"Category: {r['category']}")
    if r["tags"]:
        lines.append(f"Tags: {join(r['tags'])}")
    price = price_text(r["is_free"], r["price"], r["currency"])
    if price:
        lines.append(f"Price: {price}")
    if r["description"]:
        lines.append(r["description"].strip())
    return "\n".join(lines)


def place_to_text(r):
    lines = [f"Venue: {r['name']}"]
    if r["category"]:
        lines.append(f"Type: {r['category']}")
    if r["area"]:
        lines.append(f"Area: {r['area']}")
    if r["address"]:
        lines.append(f"Address: {r['address']}")
    if r["cuisines"]:
        lines.append(f"Cuisines: {join(r['cuisines'])}")
    if r["tags"]:
        lines.append(f"Tags: {join(r['tags'])}")
    if r["price_range"]:
        lines.append(f"Price range: {r['price_range']}")
    if r["languages"]:
        lines.append(f"Languages spoken: {join(r['languages'])}")
    if isinstance(r["opening_hours"], dict) and r["opening_hours"]:
        hours = "; ".join(f"{day}: {h}" for day, h in r["opening_hours"].items())
        lines.append(f"Opening hours: {hours}")
    if r["description"]:
        lines.append(r["description"].strip())
    return "\n".join(lines)


def tour_to_text(r):
    lines = [f"Tour: {r['name']}"]
    if r["category"]:
        lines.append(f"Type: {r['category']}")
    if r["duration"]:
        lines.append(f"Duration: {r['duration']}")
    if r["departure_times"]:
        lines.append(f"Departures: {join(r['departure_times'])}")
    if r["meeting_point"]:
        lines.append(f"Meeting point: {r['meeting_point']}")
    if r["languages"]:
        lines.append(f"Languages: {join(r['languages'])}")
    if r["included"]:
        lines.append(f"Included: {join(r['included'])}")
    price = price_text(False, r["price"], r["currency"])
    if price:
        lines.append(f"Price: {price}")
    if r["description"]:
        lines.append(r["description"].strip())
    return "\n".join(lines)


def build_documents(events, places, tours):
    docs = []
    for r in events:
        docs.append({
            "source_type": "event", "source_id": r["id"], "title": r["name"],
            "content": event_to_text(r), "area": r["area"],
            "event_date": r["date"], "is_recurring": bool(r["recurrence_days"]),
            "url": r["ticket_url"],
        })
    for r in places:
        docs.append({
            "source_type": "place", "source_id": r["id"], "title": r["name"],
            "content": place_to_text(r), "area": r["area"],
            "event_date": None, "is_recurring": False, "url": r["website"],
        })
    for r in tours:
        docs.append({
            "source_type": "tour", "source_id": r["id"], "title": r["name"],
            "content": tour_to_text(r), "area": None,
            "event_date": None, "is_recurring": False, "url": r["booking_url"],
        })
    return docs


UPSERT_SQL = """
INSERT INTO ai_documents
    (source_type, source_id, title, content, area, event_date, is_recurring, url, embedding, updated_at)
VALUES
    (%(source_type)s, %(source_id)s, %(title)s, %(content)s, %(area)s,
     %(event_date)s, %(is_recurring)s, %(url)s, %(embedding)s::vector, now())
ON CONFLICT (source_type, source_id) DO UPDATE SET
    title = EXCLUDED.title, content = EXCLUDED.content, area = EXCLUDED.area,
    event_date = EXCLUDED.event_date, is_recurring = EXCLUDED.is_recurring,
    url = EXCLUDED.url, embedding = EXCLUDED.embedding, updated_at = now()
"""


def main():
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        conn.execute(SETUP_SQL)

        events = conn.execute(EVENTS_SQL).fetchall()
        places = conn.execute(PLACES_SQL).fetchall()
        tours = conn.execute(TOURS_SQL).fetchall()
        print(f"Read {len(events)} events, {len(places)} places, {len(tours)} tours")

        docs = build_documents(events, places, tours)
        if not docs:
            print("Nothing to sync.")
            return

        print("Example document:\n" + "-" * 40 + "\n" + docs[0]["content"] + "\n" + "-" * 40)

        vectors = embed_many([d["content"] for d in docs], show_progress=True)
        for d, v in zip(docs, vectors):
            d["embedding"] = to_pgvector(v)

        with conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, docs)

            # Remove documents whose source row is no longer active / upcoming
            for source_type in ("event", "place", "tour"):
                keep = [d["source_id"] for d in docs if d["source_type"] == source_type]
                cur.execute(
                    "DELETE FROM ai_documents WHERE source_type = %s AND NOT (source_id = ANY(%s))",
                    (source_type, keep),
                )

        conn.commit()
        print(f"Synced {len(docs)} documents into ai_documents ({date.today()})")


if __name__ == "__main__":
    main()
