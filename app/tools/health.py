# app/tools/health.py
# Pharmacies, health centres, hospitals and dentists from the Cabildo de Tenerife's register
# (loaded by ingest/sync_health.py).
#
# The one question here where being wrong or slow actually hurts someone, so it answers from
# local data rather than a live third-party call, and it gives the phone number every time —
# opening hours are not in the register, and on an island where much of it shuts for siesta,
# "ring first" is the honest advice.

import psycopg
from psycopg.rows import dict_row

from app import config
from app.tools._located import LOCATION_PARAMS, resolve

# What people ask for -> what the register calls it.
KINDS = {
    "pharmacy": "farmacia",
    "health_centre": "centro de salud",
    "hospital": "servicios hospitalarios",
    "dentist": "clinica dental",
    "physiotherapy": "fisioterapia rehabilitacion",
    "vet": "servicios veterinarios",
    "laboratory": "laboratorio analisis clinicos",
}

_M_PER_DEG_LAT = 111_320


def find_health_service(place=None, latitude=None, longitude=None, kind="pharmacy", limit=5):
    """Nearest pharmacies or other health services to a place in Tenerife."""
    lat, lon, where = resolve(place, latitude, longitude)
    if lat is None:
        return where

    db_kind = KINDS.get(kind, kind)
    import math
    mlon = _M_PER_DEG_LAT * math.cos(math.radians(lat))

    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute(
            """SELECT name, address, municipality, phone, website,
                      sqrt(((latitude - %(lat)s) * %(mlat)s) ^ 2 +
                           ((longitude - %(lon)s) * %(mlon)s) ^ 2) AS metres
               FROM tenerife_health_services
               WHERE kind = %(kind)s
               ORDER BY metres
               LIMIT %(limit)s""",
            {"lat": lat, "lon": lon, "mlat": _M_PER_DEG_LAT, "mlon": mlon,
             "kind": db_kind, "limit": max(1, min(int(limit), 10))},
        ).fetchall()

    if not rows:
        return (f"Nothing of type {kind!r} in the register. Known kinds: "
                f"{', '.join(KINDS)}.")

    label = {"pharmacy": "Pharmacies", "hospital": "Hospitals",
             "health_centre": "Health centres", "dentist": "Dentists"}.get(kind, kind.title())
    lines = [f"{label} nearest to {where.split(',')[0]}:"]
    for r in rows:
        distance = (f"{r['metres'] / 1000:.1f} km" if r["metres"] >= 1000
                    else f"{r['metres']:.0f} m")
        line = f"  {r['name']} — {r['address']}, {r['municipality']} ({distance})"
        if r["phone"]:
            line += f", tel {r['phone']}"
        lines.append(line)
    lines.append("Opening hours are not in the register — ring before setting off. "
                 "For an emergency call 112.")
    return "\n".join(lines)


TOOLS = {
    "find_health_service": {
        "description": (
            "Nearest pharmacy, health centre, hospital, dentist, physiotherapist, vet or "
            "clinical laboratory to a place in Tenerife, with address, phone and distance. "
            "Official Cabildo de Tenerife register. kind defaults to 'pharmacy'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                **LOCATION_PARAMS,
                "kind": {"type": "string",
                         "description": "pharmacy | health_centre | hospital | dentist | "
                                        "physiotherapy | vet | laboratory"},
                "limit": {"type": "integer", "description": "How many to list (default 5)"},
            },
            "required": [],
        },
        "run": find_health_service,
    },
}
