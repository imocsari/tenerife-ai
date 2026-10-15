# app/tools/weather.py
# Current conditions and a short forecast from Open-Meteo. Free, no key, no account.
#
# Takes coordinates rather than a place name, so the model is expected to call
# geocode_place first. That split is deliberate: one tool that does both would hide the
# lookup, and when a place resolves to the wrong spot it should be visible as its own step.

import requests

from app.tools._cache import cached

FORECAST = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo returns WMO weather codes; these are the ones the Canaries actually produce.
WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snowfall", 73: "moderate snowfall", 75: "heavy snowfall",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


@cached()
def get_weather(place=None, latitude=None, longitude=None, days=3):
    """Current weather and a short daily forecast for one point in Tenerife.

    Accepts either a place name or coordinates. The place name path exists because small
    local models reliably fail the two-step chain (2026-10-14: qwen2.5:7b called
    geocode_place, got the coordinates, then told the user to call get_weather themselves
    instead of calling it). Letting one tool answer "weather in Los Gigantes" end to end
    removes the step they cannot take, while coordinates still work for models that chain.
    """
    days = max(1, min(int(days), 7))
    if latitude is None or longitude is None:
        if not place:
            return "Give me either a place name or both latitude and longitude."
        from app.tools.geocode import geocode_place
        located = geocode_place(place)
        try:
            latitude = float([l for l in located.splitlines() if l.startswith("latitude")][0].split(": ")[1])
            longitude = float([l for l in located.splitlines() if l.startswith("longitude")][0].split(": ")[1])
        except (IndexError, ValueError):
            return located   # the geocoder's own "no such place" message
        where = located.splitlines()[0]
    else:
        where = f"{float(latitude):.4f}, {float(longitude):.4f}"
    res = requests.get(
        FORECAST,
        params={
            "latitude": latitude, "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max",
            "timezone": "Atlantic/Canary",
            "forecast_days": days,
        },
        timeout=10,
    )
    res.raise_for_status()
    d = res.json()

    c = d.get("current", {})
    lines = [
        f"Weather for {where}",
        "Now: "
        f"{c.get('temperature_2m')}°C (feels like {c.get('apparent_temperature')}°C), "
        f"{WMO.get(c.get('weather_code'), 'unknown conditions')}, "
        f"humidity {c.get('relative_humidity_2m')}%, wind {c.get('wind_speed_10m')} km/h",
        "",
        "Forecast:",
    ]
    day = d.get("daily", {})
    for i, date in enumerate(day.get("time", [])):
        lines.append(
            f"  {date}: {day['temperature_2m_min'][i]}–{day['temperature_2m_max'][i]}°C, "
            f"{WMO.get(day['weather_code'][i], 'unknown')}, "
            f"rain chance {day['precipitation_probability_max'][i]}%, "
            f"UV index {day['uv_index_max'][i]}"
        )
    return "\n".join(lines)


@cached()
def get_sun_times(place=None, latitude=None, longitude=None, days=1):
    """Sunrise and sunset for a place in Tenerife.

    Its own tool rather than a line inside the forecast because it is asked on its own, and
    for a reason specific to here: the island is far enough west in its timezone that sunset
    runs late, and watching it from the west coast is a fixture of a visit.
    """
    from app.tools._located import resolve
    lat, lon, where = resolve(place, latitude, longitude)
    if lat is None:
        return where

    res = requests.get(FORECAST, params={
        "latitude": lat, "longitude": lon,
        "daily": "sunrise,sunset,daylight_duration",
        "timezone": "Atlantic/Canary",
        "forecast_days": max(1, min(int(days), 7)),
    }, timeout=10)
    res.raise_for_status()
    day = res.json().get("daily", {})

    lines = [f"Sun times for {where}"]
    for i, date_str in enumerate(day.get("time", [])):
        hours = (day.get("daylight_duration") or [0])[i] / 3600
        lines.append(f"  {date_str}: sunrise {day['sunrise'][i][11:16]}, "
                     f"sunset {day['sunset'][i][11:16]} ({hours:.1f} h of daylight)")
    return "\n".join(lines)


TOOLS = {
    "get_weather": {
        "description": (
            "Current weather and a short daily forecast for somewhere in Tenerife. Just pass "
            "the place name, e.g. place='Los Gigantes' — it looks up the coordinates itself. "
            "Pass latitude and longitude instead only if you already have them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place": {"type": "string", "description": "Place name, e.g. 'Los Gigantes'"},
                "latitude": {"type": "number", "description": "Latitude, if already known"},
                "longitude": {"type": "number", "description": "Longitude, if already known"},
                "days": {"type": "integer", "description": "How many days to forecast, 1-7 (default 3)"},
            },
            "required": [],
        },
        "run": get_weather,
    },
    "get_sun_times": {
        "description": (
            "Sunrise and sunset times for a place in Tenerife. Pass the place name; it finds "
            "the coordinates itself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place": {"type": "string", "description": "Place name, e.g. 'Los Gigantes'"},
                "latitude": {"type": "number", "description": "Latitude, if already known"},
                "longitude": {"type": "number", "description": "Longitude, if already known"},
                "days": {"type": "integer", "description": "How many days, 1-7 (default 1)"},
            },
            "required": [],
        },
        "run": get_sun_times,
    },
}
