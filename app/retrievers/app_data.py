# app/retrievers/app_data.py
# Searches your app's events, places and tours (ai_documents table in Supabase),
# combining exact filters (area, dates, type) with meaning search (pgvector).

import psycopg
from psycopg.rows import dict_row

from app import config
from app.embeddings import to_pgvector


def search(query_vector, top_k=5, area=None, date_from=None, date_to=None, source_type=None):
    if not config.DATABASE_URL:
        return []

    vector = to_pgvector(query_vector)

    # Never return events that are already over (unless they repeat)
    where = ["(source_type <> 'event' OR is_recurring OR event_date >= CURRENT_DATE)"]
    params = []
    if area:
        where.append("area ILIKE %s")
        params.append(f"%{area}%")
    if source_type:
        where.append("source_type = %s")
        params.append(source_type)
    if date_from:
        where.append("(source_type <> 'event' OR is_recurring OR event_date >= %s)")
        params.append(date_from)
    if date_to:
        where.append("(source_type <> 'event' OR is_recurring OR event_date <= %s)")
        params.append(date_to)

    sql = f"""
        SELECT source_type, title, content, url,
               1 - (embedding <=> %s::vector) AS score
        FROM ai_documents
        WHERE {' AND '.join(where)}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    # Note: one connection per search is fine for now; use a connection pool in production.
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute(sql, [vector, *params, vector, top_k]).fetchall()

    return [{
        "type": r["source_type"],
        "title": r["title"],
        "content": r["content"],
        "url": r["url"],
        "score": float(r["score"]),
    } for r in rows]
