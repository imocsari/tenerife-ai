# app/tools/places_nearby.py
# Everyday places near you — nail bars, hairdressers, supermarkets, launderettes, ATMs,
# viewpoints — from Overture Maps (loaded by ingest/sync_overture_places.py).
#
# This fills a real hole rather than duplicating TenerInfo's own data. TenerInfo knows bars,
# restaurants, nightlife and events, because that is what it is for; asked where to get your
# nails done it had one match, and that was a nightclub called Salon Jacaranda. search_tenerinfo
# stays the first choice for anything it does cover — this is for the ordinary errands of a
# fortnight on the island.

import math

from app import config
from app.db import connection
from app.tools._located import LOCATION_PARAMS, resolve

_M_PER_DEG_LAT = 111_320

# What people say -> what Overture calls it. Several words map to one category, and a few map
# to more than one, because "hairdresser" should find barbers too.
ALIASES = {
    "nails": ["nail_salon"], "nail salon": ["nail_salon"], "manicure": ["nail_salon"],
    "beauty": ["beauty_salon", "nail_salon", "spa"], "spa": ["spa", "massage"],
    "massage": ["massage", "spa"],
    "hairdresser": ["hair_salon", "barber"], "barber": ["barber", "hair_salon"],
    "haircut": ["hair_salon", "barber"],
    "supermarket": ["supermarket", "grocery_store"], "groceries": ["supermarket", "grocery_store"],
    "shop": ["supermarket", "grocery_store", "shopping_center"],
    "bakery": ["bakery"], "butcher": ["butcher"],
    "laundry": ["laundry", "dry_cleaning"], "launderette": ["laundry", "dry_cleaning"],
    "atm": ["atm"], "cash": ["atm", "bank"], "bank": ["bank", "atm"],
    "post office": ["post_office"], "post": ["post_office"],
    "car hire": ["car_rental"], "car rental": ["car_rental"], "car wash": ["car_wash"],
    "petrol": ["gas_station"], "petrol station": ["gas_station"],
    "shopping": ["shopping_center", "market"], "market": ["market", "shopping_center"],
    "viewpoint": ["viewpoint"], "mirador": ["viewpoint"],
    "tourist information": ["tourist_information"],
    "gym": ["gym"], "golf": ["golf_course"], "playground": ["playground"],
    "library": ["library"], "cinema": ["cinema"], "museum": ["museum"],
}


def _categories_for(what):
    key = (what or "").strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    # Fall back to anything whose alias or category name contains the words given.
    hits = {c for phrase, cats in ALIASES.items() if key and key in phrase for c in cats}
    return sorted(hits) or [key.replace(" ", "_")]


def find_places_nearby(what, place=None, latitude=None, longitude=None, limit=6):
    """Nearest nail bars, hairdressers, supermarkets, ATMs and the like to a place."""
    lat, lon, where = resolve(place, latitude, longitude)
    if lat is None:
        return where

    categories = _categories_for(what)
    mlon = _M_PER_DEG_LAT * math.cos(math.radians(lat))

    with connection() as conn:
        rows = conn.execute(
            """SELECT name, category, locality, address, phone, website,
                      sqrt(((latitude - %(lat)s) * %(mlat)s) ^ 2 +
                           ((longitude - %(lon)s) * %(mlon)s) ^ 2) AS metres
               FROM overture_places
               WHERE category = ANY(%(cats)s)
               ORDER BY metres
               LIMIT %(limit)s""",
            {"lat": lat, "lon": lon, "mlat": _M_PER_DEG_LAT, "mlon": mlon,
             "cats": categories, "limit": max(1, min(int(limit), 10))},
        ).fetchall()

    if not rows:
        return (f"Nothing found for {what!r} near {where.split(',')[0]}. "
                f"Known kinds include: nails, hairdresser, supermarket, bakery, laundry, atm, "
                f"post office, car hire, viewpoint, gym, museum.")

    lines = [f"{what.title()} nearest to {where.split(',')[0]}:"]
    for r in rows:
        distance = f"{r['metres'] / 1000:.1f} km" if r["metres"] >= 1000 else f"{r['metres']:.0f} m"
        bits = [f"  {r['name']}"]
        if r["address"]:
            bits.append(r["address"])
        if r["locality"]:
            bits.append(r["locality"])
        line = " — ".join(bits[:2]) + (f", {r['locality']}" if r["locality"] and len(bits) > 2 else "")
        line += f" ({distance})"
        if r["phone"]:
            line += f", tel {r['phone']}"
        lines.append(line)
    lines.append("Source: Overture Maps. Opening hours are not included — ring first.")
    return "\n".join(lines)


TOOLS = {
    "find_places_nearby": {
        "description": (
            "Find everyday places near somewhere in Tenerife that TenerInfo's own venue data "
            "does not cover: nail salons, hairdressers, barbers, spas, supermarkets, bakeries, "
            "launderettes, ATMs, banks, post offices, car hire, viewpoints, gyms, museums, "
            "cinemas. Use search_tenerinfo first for bars, restaurants, nightlife and events — "
            "this is for errands and services."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {"type": "string",
                         "description": "What is wanted, e.g. 'nails', 'hairdresser', 'supermarket', 'atm'"},
                **LOCATION_PARAMS,
                "limit": {"type": "integer", "description": "How many to list (default 6)"},
            },
            "required": ["what"],
        },
        "run": find_places_nearby,
    },
}
