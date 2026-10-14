# app/tools/marine.py
# Sea conditions from Open-Meteo's marine API. Free, no key.
#
# Relevant here in a way it would not be inland: the west coast (Los Gigantes, Playa Santiago)
# is where whale and dolphin boats go out, and swell decides whether they sail.

import requests

from app.tools._located import LOCATION_PARAMS, resolve

MARINE = "https://marine-api.open-meteo.com/v1/marine"


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
}
