# app/tools/_located.py
# Turning a place name into coordinates, from data we already hold.
#
# This used to call OpenStreetMap's Nominatim on every lookup. That worked from a laptop and
# was the wrong dependency for a deployed service: Nominatim's usage policy prohibits bulk and
# cloud use and they block datacenter ranges, so the first production deploy could search
# TenerInfo's own events happily while every weather, sea or fuel question failed — the only
# difference being that those need a place resolved first.
#
# The coordinates were local all along: 37 areas and ~1,400 venues in the app's own places
# table, 3,623 Overture places, 3,897 TITSA stops. Resolving against those is faster, needs no
# third party's goodwill, and knows local names a global gazetteer does not. Nominatim stays as
# a last resort for anything genuinely unknown.

from app.db import connection

# Everything this assistant answers is about one island, so a coordinate outside it is wrong by
# definition rather than merely unexpected. Nominatim's viewbox only *prefers* a region: asked
# for "Las Cañadas del Teide" it happily returned 40.29, -3.75 — a spot near Madrid — and the
# forecast call then failed on coordinates nobody would have questioned if it had not.
TENERIFE_BOUNDS = (27.95, 28.65, -17.00, -16.05)   # south, north, west, east


def _in_tenerife(lat, lon):
    south, north, west, east = TENERIFE_BOUNDS
    return south <= lat <= north and west <= lon <= east

# Ranked: an area centroid beats a single venue that happens to share the name, and TenerInfo's
# own data beats Overture's. Ties break on how closely the name matches.
RESOLVE_SQL = """
WITH candidates AS (
    -- An area, as the centre of everything we know in it. "Los Cristianos" is an area, not a
    -- point, and the middle of its 212 venues is a better answer than any one of them.
    SELECT 1 AS rank, area AS label, avg(latitude) AS lat, avg(longitude) AS lon,
           (lower(area) = lower(%(q)s)) AS exact
    FROM places
    WHERE is_active AND area IS NOT NULL AND latitude IS NOT NULL
      AND unaccent(area) ILIKE unaccent(%(like)s)
    GROUP BY area

    UNION ALL
    SELECT 2, name, latitude, longitude, (lower(name) = lower(%(q)s))
    FROM places
    WHERE is_active AND latitude IS NOT NULL AND unaccent(name) ILIKE unaccent(%(like)s)

    UNION ALL
    SELECT 3, name, latitude, longitude, (lower(name) = lower(%(q)s))
    FROM overture_places
    WHERE unaccent(name) ILIKE unaccent(%(like)s)

    UNION ALL
    SELECT 4, stop_name, latitude, longitude, (lower(stop_name) = lower(%(q)s))
    FROM titsa_stops
    WHERE latitude IS NOT NULL AND unaccent(stop_name) ILIKE unaccent(%(like)s)
)
SELECT label, lat, lon FROM candidates
ORDER BY exact DESC, rank, length(label)
LIMIT 1
"""


def _from_our_data(place):
    try:
        with connection() as conn:
            row = conn.execute(RESOLVE_SQL,
                               {"q": place, "like": f"%{place}%"}).fetchone()
    except Exception as e:                      # a database hiccup should fall through, not fail
        print(f"[resolve] local lookup failed for {place!r}: {type(e).__name__}: {e}", flush=True)
        return None
    if not row or row["lat"] is None:
        return None
    return float(row["lat"]), float(row["lon"]), row["label"]


def resolve(place=None, latitude=None, longitude=None):
    """-> (latitude, longitude, label) or (None, None, message_for_the_model)."""
    if latitude is not None and longitude is not None:
        return float(latitude), float(longitude), f"{float(latitude):.4f}, {float(longitude):.4f}"
    if not place:
        return None, None, "Give me either a place name or both latitude and longitude."

    local = _from_our_data(place)
    if local:
        return local

    # Try the distinctive words on their own. "Las Cañadas del Teide" matches nothing we hold
    # as a whole string, while "Teide" matches exactly — and a global gazetteer asked for the
    # full phrase cheerfully answered with a spot near Madrid. Longest word first, since that
    # is usually the proper noun rather than the scaffolding around it.
    STOPWORDS = {"las", "los", "del", "de", "la", "el", "playa", "puerto", "san", "santa"}
    words = sorted((w for w in place.replace(",", " ").split()
                    if len(w) > 3 and w.lower() not in STOPWORDS),
                   key=len, reverse=True)
    for word in words[:2]:
        local = _from_our_data(word)
        if local:
            lat, lon, label = local
            return lat, lon, label

    # Nothing we hold matches — ask Nominatim, which may well refuse from a datacenter.
    from app.tools.geocode import geocode_place
    located = geocode_place(place)
    try:
        lat = float([l for l in located.splitlines() if l.startswith("latitude")][0].split(": ")[1])
        lon = float([l for l in located.splitlines() if l.startswith("longitude")][0].split(": ")[1])
    except (IndexError, ValueError):
        return None, None, (f"I could not work out where {place!r} is. "
                            "Try a nearby town or resort name.")
    if not _in_tenerife(lat, lon):
        print(f"[resolve] {place!r} geocoded to {lat:.4f},{lon:.4f} — outside Tenerife, rejected",
              flush=True)
        return None, None, (f"I could only find {place!r} outside Tenerife, so I have not used "
                            "it. Try a Tenerife town, resort or landmark.")
    return lat, lon, located.splitlines()[0]


LOCATION_PARAMS = {
    "place": {"type": "string", "description": "Place name, e.g. 'Los Gigantes'"},
    "latitude": {"type": "number", "description": "Latitude, if already known"},
    "longitude": {"type": "number", "description": "Longitude, if already known"},
}
