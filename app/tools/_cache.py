# app/tools/_cache.py
# A small time-boxed cache for the read-only HTTP tools.
#
# Weather, sea, air quality and fuel prices change on the order of an hour; questions arrive
# far faster than that, and several questions in one conversation often hit the same place.
# Re-fetching each time adds a second of latency and load on free APIs that are being generous.
#
# Deliberately not applied to buses or events: a timetable answer that is half an hour stale
# is a missed bus, and events change the moment the scrapers publish.

import time
from functools import wraps

from app import config


def cached(seconds=None):
    """Memoise on the arguments, for a while. Failures are never cached — a transient outage
    should not be remembered as an answer for the next half hour."""
    def decorate(fn):
        store = {}

        @wraps(fn)
        def wrapper(*args, **kwargs):
            ttl = config.API_CACHE_SECONDS if seconds is None else seconds
            key = (args, tuple(sorted(kwargs.items())))
            hit = store.get(key)
            now = time.monotonic()
            if hit and now - hit[0] < ttl:
                return hit[1]
            value = fn(*args, **kwargs)
            store[key] = (now, value)
            if len(store) > 512:                      # bounded; drop the oldest half
                for k in sorted(store, key=lambda k: store[k][0])[:256]:
                    store.pop(k, None)
            return value
        wrapper.cache_clear = store.clear
        return wrapper
    return decorate
