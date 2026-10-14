# app/tools/air_quality.py
# Air quality from Open-Meteo. Free, no key.
#
# The reason this matters in Tenerife is calima — Saharan dust blown over from Africa, which
# can take PM10 from negligible to hazardous within hours, closes schools, grounds flights and
# is the single most common "should I go outside today" question on the island. The dust field
# is reported explicitly rather than hidden inside a general index.

import requests

from app.tools._located import LOCATION_PARAMS, resolve

AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _band(aqi):
    if aqi is None:
        return "unknown"
    for limit, label in ((20, "good"), (40, "fair"), (60, "moderate"),
                         (80, "poor"), (100, "very poor")):
        if aqi <= limit:
            return label
    return "extremely poor"


def get_air_quality(place=None, latitude=None, longitude=None):
    """Current air quality, including Saharan dust (calima), for a point in Tenerife."""
    lat, lon, where = resolve(place, latitude, longitude)
    if lat is None:
        return where

    res = requests.get(
        AIR,
        params={
            "latitude": lat, "longitude": lon,
            "current": "european_aqi,pm10,pm2_5,dust,uv_index",
            "timezone": "Atlantic/Canary",
        },
        timeout=10,
    )
    res.raise_for_status()
    c = res.json().get("current", {})
    aqi = c.get("european_aqi")
    dust = c.get("dust")

    lines = [
        f"Air quality for {where}",
        f"European AQI {aqi} ({_band(aqi)})",
        f"PM10 {c.get('pm10')} µg/m³, PM2.5 {c.get('pm2_5')} µg/m³, UV index {c.get('uv_index')}",
        f"Saharan dust {dust} µg/m³",
    ]
    # Calima is the thing people actually want to know about; say so in words.
    if dust is not None:
        if dust >= 200:
            lines.append("That is a heavy calima — poor visibility, and hard going for anyone "
                         "with asthma or breathing problems.")
        elif dust >= 50:
            lines.append("There is noticeable calima (Saharan dust) in the air today.")
    return "\n".join(lines)


TOOLS = {
    "get_air_quality": {
        "description": (
            "Current air quality for a point in Tenerife, including Saharan dust (calima), "
            "which regularly affects the island and matters for asthma, hiking and visibility. "
            "Pass the place name; it finds the coordinates itself."
        ),
        "parameters": {"type": "object", "properties": dict(LOCATION_PARAMS), "required": []},
        "run": get_air_quality,
    },
}
