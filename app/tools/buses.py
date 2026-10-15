# app/tools/buses.py
# Bus departures from TITSA's real timetable (loaded by ingest/sync_titsa.py).
#
# Two queries cover what people actually ask: "when's the next bus from A to B", and "what
# goes from A at all". Both are answered against today's running services, because a bus that
# exists in the timetable but does not run today is a wrong answer dressed as a right one.

from datetime import date, datetime

import psycopg
from psycopg.rows import dict_row

from app import config

# A GTFS service day runs past midnight: a 00:40 bus is listed at 24:40 on the previous day.
# So "now" has to be expressed the same way, or the last buses of the night disappear.
SERVICE_DAY_ROLLOVER_HOUR = 4


def _now_seconds_and_date():
    now = datetime.now()
    if now.hour < SERVICE_DAY_ROLLOVER_HOUR:
        # Early hours still belong to yesterday's service day, offset past 24:00.
        return (now.hour + 24) * 3600 + now.minute * 60, date.fromordinal(now.toordinal() - 1)
    return now.hour * 3600 + now.minute * 60, now.date()


def _connect():
    """Borrows from the shared pool — see app/db.py."""
    from app.db import connection
    return connection()


# How far from a place a bus stop can be and still count as serving it. 1km is about a
# 12-minute walk — generous, but a resort's stops are often named after the street rather
# than the resort, so being strict here just means finding nothing.
NEARBY_RADIUS_M = 1000
_M_PER_DEG_LAT = 111_320


def _resolve_stops(conn, text):
    """Which stop_ids does the user mean? -> (ids, label) or ([], explanation).

    Name matching first, accent-insensitively, because TITSA writes AMÉRICAS and nobody
    types that. When the name finds nothing, fall back to geography: geocode the place and
    take the stops around it. That fallback is what makes ordinary resort names work at all —
    there is no TITSA stop called "Playa de las Américas"; its stops are named after streets
    and landmarks, so no spelling of the resort would ever have matched.
    """
    rows = conn.execute(
        """SELECT stop_id, stop_name FROM titsa_stops
           WHERE unaccent(stop_name) ILIKE unaccent(%(like)s)
           ORDER BY (unaccent(stop_name) ILIKE unaccent(%(prefix)s)) DESC, length(stop_name)
           LIMIT 12""",
        {"like": f"%{text}%", "prefix": f"{text}%"},
    ).fetchall()
    if rows:
        return [r["stop_id"] for r in rows], rows[0]["stop_name"]

    from app.tools._located import resolve
    lat, lon, label = resolve(place=text)
    if lat is None:
        return [], label

    # A bounding box, then true distance within it: enough for a 1km radius, and it uses the
    # plain lat/lon columns rather than requiring PostGIS.
    d_lat = NEARBY_RADIUS_M / _M_PER_DEG_LAT
    d_lon = d_lat / max(0.1, abs(__import__("math").cos(__import__("math").radians(lat))))
    rows = conn.execute(
        """SELECT stop_id, stop_name,
                  ((latitude - %(lat)s) * %(mlat)s) ^ 2 +
                  ((longitude - %(lon)s) * %(mlon)s) ^ 2 AS d2
           FROM titsa_stops
           WHERE latitude BETWEEN %(lat)s - %(dlat)s AND %(lat)s + %(dlat)s
             AND longitude BETWEEN %(lon)s - %(dlon)s AND %(lon)s + %(dlon)s
           ORDER BY d2 LIMIT 12""",
        {"lat": lat, "lon": lon, "dlat": d_lat, "dlon": d_lon,
         "mlat": _M_PER_DEG_LAT,
         "mlon": _M_PER_DEG_LAT * __import__("math").cos(__import__("math").radians(lat))},
    ).fetchall()
    if not rows:
        return [], f"No TITSA stops within {NEARBY_RADIUS_M}m of {label}."
    return [r["stop_id"] for r in rows], f"{label.split(',')[0]} (nearest stops)"


def _fmt(seconds_value, text):
    """24:40 reads as 00:40 to a human; keep the real clock time in the answer."""
    if seconds_value is not None and seconds_value >= 24 * 3600:
        return f"{(seconds_value // 3600) - 24:02d}:{(seconds_value % 3600) // 60:02d} (after midnight)"
    return (text or "")[:5]


def find_bus_stop(name):
    """Find TITSA bus stops whose name matches, to check spelling before asking for departures."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT stop_name, stop_id FROM titsa_stops "
            "WHERE unaccent(stop_name) ILIKE unaccent(%s) "
            "ORDER BY length(stop_name) LIMIT 15", (f"%{name}%",)).fetchall()
    if not rows:
        return f"No TITSA bus stop matches {name!r}."
    return "Matching stops:\n" + "\n".join(f"  {r['stop_name']}" for r in rows)


def get_next_buses(from_stop, to_stop=None, limit=6):
    """Next departures from a stop today, optionally only those continuing to another stop."""
    now_seconds, service_date = _now_seconds_and_date()
    limit = max(1, min(int(limit), 15))

    with _connect() as conn:
        from_ids, from_label = _resolve_stops(conn, from_stop)
        if not from_ids:
            return f"Could not find a bus stop for {from_stop!r}. {from_label or ''}".strip()
        to_ids, to_label = ([], None)
        if to_stop:
            to_ids, to_label = _resolve_stops(conn, to_stop)
            if not to_ids:
                return f"Could not find a bus stop for {to_stop!r}. {to_label or ''}".strip()

    if to_stop:
        sql = """
            SELECT r.short_name AS route, t.headsign,
                   o.departure_text AS dep_text, o.departure_seconds AS dep_s,
                   d.departure_text AS arr_text, d.departure_seconds AS arr_s,
                   so.stop_name AS from_name, sd.stop_name AS to_name
            FROM titsa_stop_times o
            JOIN titsa_stop_times d ON d.trip_id = o.trip_id AND d.stop_sequence > o.stop_sequence
            JOIN titsa_stops so ON so.stop_id = o.stop_id
            JOIN titsa_stops sd ON sd.stop_id = d.stop_id
            JOIN titsa_trips t  ON t.trip_id  = o.trip_id
            JOIN titsa_routes r ON r.route_id = t.route_id
            WHERE o.stop_id = ANY(%(from_ids)s)
              AND d.stop_id = ANY(%(to_ids)s)
              AND o.departure_seconds >= %(now)s
              AND t.service_id IN (SELECT service_id FROM titsa_calendar_dates
                                   WHERE service_date = %(day)s AND exception_type = 1)
            ORDER BY o.departure_seconds
            LIMIT %(limit)s
        """
        params = {"from_ids": from_ids, "to_ids": to_ids,
                  "now": now_seconds, "day": service_date, "limit": limit}
    else:
        sql = """
            SELECT r.short_name AS route, t.headsign,
                   o.departure_text AS dep_text, o.departure_seconds AS dep_s,
                   NULL AS arr_text, NULL AS arr_s,
                   so.stop_name AS from_name, NULL AS to_name
            FROM titsa_stop_times o
            JOIN titsa_stops so ON so.stop_id = o.stop_id
            JOIN titsa_trips t  ON t.trip_id  = o.trip_id
            JOIN titsa_routes r ON r.route_id = t.route_id
            WHERE o.stop_id = ANY(%(from_ids)s)
              AND o.departure_seconds >= %(now)s
              AND t.service_id IN (SELECT service_id FROM titsa_calendar_dates
                                   WHERE service_date = %(day)s AND exception_type = 1)
            ORDER BY o.departure_seconds
            LIMIT %(limit)s
        """
        params = {"from_ids": from_ids, "now": now_seconds,
                  "day": service_date, "limit": limit}

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    if not rows:
        where = f" to {to_stop}" if to_stop else ""
        return (f"No more buses today from {from_stop}{where}. Either the stop name does not "
                f"match (try find_bus_stop) or the last one has gone.")

    header = f"Next buses from {rows[0]['from_name']}"
    if to_stop and rows[0]["to_name"]:
        header += f" to {rows[0]['to_name']}"
    lines = [header + f" (today, {service_date}):"]
    for r in rows:
        line = f"  {_fmt(r['dep_s'], r['dep_text'])}  line {r['route']} → {r['headsign']}"
        if r["arr_s"] is not None:
            mins = (r["arr_s"] - r["dep_s"]) // 60
            line += f", arrives {_fmt(r['arr_s'], r['arr_text'])} ({mins} min)"
        lines.append(line)
    return "\n".join(lines)


TOOLS = {
    "get_next_buses": {
        "description": (
            "Next TITSA bus departures today from a stop, optionally only those continuing to "
            "a second stop. Use for 'how do I get from X to Y' or 'when is the next bus'. "
            "Stop names are places, e.g. 'Los Cristianos', 'Costa Adeje'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "from_stop": {"type": "string", "description": "Where the journey starts, e.g. 'Los Cristianos'"},
                "to_stop": {"type": "string", "description": "Optional destination, e.g. 'Costa Adeje'"},
                "limit": {"type": "integer", "description": "How many departures to list (default 6)"},
            },
            "required": ["from_stop"],
        },
        "run": get_next_buses,
    },
    "find_bus_stop": {
        "description": (
            "Find TITSA bus stops whose name contains some text. Use when get_next_buses finds "
            "nothing, to check what the stop is actually called."
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Part of a stop name"}},
            "required": ["name"],
        },
        "run": find_bus_stop,
    },
}
