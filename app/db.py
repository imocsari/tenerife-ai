# app/db.py
# One connection pool for the whole app.
#
# Every tool was opening its own connection and closing it again. Against Supabase's pooler
# that is a TCP handshake plus TLS plus auth on every question — tens of milliseconds each,
# several per answer — and under any real traffic it is also a good way to exhaust the
# connection limit. The pool opens a couple at startup and hands them round.

from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config

_pool = None


def pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            config.DATABASE_URL, min_size=1, max_size=5,
            kwargs={"row_factory": dict_row},
            open=True, timeout=15,
        )
    return _pool


@contextmanager
def connection():
    """Borrow a connection. Falls back to a direct one if the pool cannot be built, so a
    pooling problem degrades to the old behaviour rather than taking the app down."""
    try:
        with pool().connection() as conn:
            yield conn
    except Exception:
        import psycopg
        with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
            yield conn
