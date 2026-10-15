# app/tools/marine.py
# Sea conditions from Open-Meteo's marine API. Free, no key.
#
# Relevant here in a way it would not be inland: the west coast (Los Gigantes, Playa Santiago)
# is where whale and dolphin boats go out, and swell decides whether they sail.

import requests

from app.tools._cache import cached

from app.tools._located import LOCATION_PARAMS, resolve

MARINE = "https://marine-api.open-meteo.com/v1/marine"


@cached()
def get_sea_conditions(place=None, latitude=None, longitude=None, days=2):
    """Wave height, wave period and sea temperature for a coastal point in Tenerife."""
    lat, lon, where = resolve(place, latitude, longitude)
    if lat is None:
        return where

    res = requests.get(
        MARINE,
        params={
            "latitude": lat, "longitude": lon,
            "current": "wave_height,wave_direction,wave_period,sea_surface_temperature",
            "daily": "wave_height_max,wave_period_max",
            "timezone": "Atlantic/Canary",
            "forecast_days": max(1, min(int(days), 7)),
        },
        timeout=10,
    )
    # The marine grid only covers water. A point inland returns 400 rather than empty data,
    # which is a normal outcome here (a town centre is often a land cell), not a failure.
    if res.status_code == 400:
        return (f"No sea data for {where} — that point is inland on the marine grid. "
                "Try somewhere on the coast, like the harbour or the beach itself.")
    res.raise_for_status()
    d = res.json()

    c = d.get("current", {})
    if c.get("wave_height") is None:
        return f"No sea data available for {where}."

    lines = [
        f"Sea conditions for {where}",
        f"Now: waves {c.get('wave_height')} m, period {c.get('wave_period')} s, "
        f"direction {c.get('wave_direction')}°, sea temperature {c.get('sea_surface_temperature')}°C",
        "",
        "Forecast:",
    ]
    day = d.get("daily", {})
    for i, date in enumerate(day.get("time", [])):
        lines.append(f"  {date}: waves up to {day['wave_height_max'][i]} m, "
                     f"period up to {day['wave_period_max'][i]} s")
    return "\n".join(lines)


@cached()
def get_tides(place=None, latitude=None, longitude=None):
    """Today's high and low water for a coastal point in Tenerife.

    Derived from Open-Meteo's hourly sea level rather than a tide-table service: there is no
    free keyless tide API for the Canaries, and the turning points of the sea-level curve are
    the high and low water. Hourly sampling means the times are good to about half an hour —
    fine for planning a walk to Garachico's rock pools, not for navigation.
    """
    lat, lon, where = resolve(place, latitude, longitude)
    if lat is None:
        return where

    res = requests.get(MARINE, params={
        "latitude": lat, "longitude": lon,
        "hourly": "sea_level_height_msl",
        "timezone": "Atlantic/Canary", "forecast_days": 1,
    }, timeout=10)
    if res.status_code == 400:
        return (f"No tide data for {where} — that point is inland on the marine grid. "
                "Try the harbour or the beach itself.")
    res.raise_for_status()
    hourly = res.json().get("hourly", {})
    times, levels = hourly.get("time", []), hourly.get("sea_level_height_msl", [])
    if not levels or all(v is None for v in levels):
        return f"No tide data available for {where}."

    turns = []
    for i in range(1, len(levels) - 1):
        a, b, c = levels[i - 1], levels[i], levels[i + 1]
        if None in (a, b, c):
            continue
        if b >= a and b >= c:
            turns.append(("High", times[i][11:16], b))
        elif b <= a and b <= c:
            turns.append(("Low", times[i][11:16], b))

    if not turns:
        return f"No clear high or low water found for {where} today."
    lines = [f"Tides today at {where} (approximate, to within about half an hour):"]
    lines += [f"  {kind} water {when} ({level:+.2f} m relative to mean sea level)"
              for kind, when, level in turns]
    return "\n".join(lines)


TOOLS = {
    "get_sea_conditions": {
        "description": (
            "Sea conditions — wave height, swell period and sea temperature — for a coastal "
            "point in Tenerife. Use for swimming, surfing, diving or whether boat trips are "
            "likely to sail. Pass the place name; it finds the coordinates itself."
        ),
        "parameters": {
            "type": "object",
            "properties": {**LOCATION_PARAMS,
                           "days": {"type": "integer", "description": "Days to forecast, 1-7 (default 2)"}},
            "required": [],
        },
        "run": get_sea_conditions,
    },
    "get_tides": {
        "description": (
            "Today's approximate high and low water for a coastal point in Tenerife — for rock "
            "pools, beach walks and snorkelling. Pass the place name."
        ),
        "parameters": {"type": "object", "properties": dict(LOCATION_PARAMS), "required": []},
        "run": get_tides,
    },
}
