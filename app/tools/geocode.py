# app/tools/geocode.py
# Turns a place name into coordinates, using OpenStreetMap's Nominatim. Free, no key.
#
# Nominatim's usage policy is strict and enforced by blocking: at most one request per
# second, and a real User-Agent identifying the application. Both are handled here —
# results are cached for the life of the process (place coordinates do not move), and
# calls are spaced out. Biased to Tenerife so "Los Gigantes" resolves to the resort
# here rather than somewhere else with the same name.

import time
from functools import lru_cache

import requests

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "TenerifeAI/1.0 (travel assistant; contact: hello@tenerinfo.app)"
TENERIFE_VIEWBOX = "-16.95,28.65,-16.10,27.95"   # west,north,east,south

_last_call = 0.0


def _throttle():
    """Nominatim allows one request a second; staying under it is our side of the deal."""
    global _last_call
    wait = 1.05 - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


@lru_cache(maxsize=256)
def geocode_place(place):
    """Find the coordinates of a place in Tenerife by name.

    Use this before asking for weather, sea conditions or air quality somewhere,
    because those need coordinates rather than a name.
    """
    _throttle()
    res = requests.get(
        NOMINATIM,
        params={
            "q": place, "format": "json", "limit": 1,
            "viewbox": TENERIFE_VIEWBOX, "bounded": 0,   # prefer Tenerife, don't forbid elsewhere
        },
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    res.raise_for_status()
    hits = res.json()
    if not hits:
        return f"No place called {place!r} was found."
    hit = hits[0]
    return (
        f"{hit.get('display_name', place)}\n"
        f"latitude: {float(hit['lat']):.4f}\n"
        f"longitude: {float(hit['lon']):.4f}"
    )


TOOLS = {
    "geocode_place": {
        "description": (
            "Find the latitude and longitude of a place in Tenerife by name "
            "(e.g. 'Los Gigantes', 'Playa de las Américas'). Call this first when you need "
            "coordinates for weather, sea or air quality."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place": {"type": "string", "description": "The place name, e.g. 'Los Cristianos'"},
            },
            "required": ["place"],
        },
        "run": geocode_place,
    },
}
