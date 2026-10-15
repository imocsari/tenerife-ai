# app/tools/stargazing.py
# Whether tonight is worth going up the mountain for.
#
# Teide sits above the inversion layer that keeps the coast under cloud, which is why the
# observatory is there and why "is tonight good for stars" is a real question with a real
# answer — the coastal forecast often says overcast while 2,000m up is clear.
#
# Cloud comes from Open-Meteo (free, keyless). Moon phase is not fetched at all: it is
# arithmetic from a known new moon, exact enough for "will moonlight wash the sky out", and
# one less service to be up.

from datetime import date, datetime, timezone

import requests

from app.tools._located import LOCATION_PARAMS, resolve

FORECAST = "https://api.open-meteo.com/v1/forecast"

# Las Cañadas / the Teide observatory side, ~2,150m — the default because it is where people
# actually go, and the coast is a different sky entirely.
TEIDE = (28.2700, -16.6300, "Las Cañadas del Teide (about 2,150m)")

# A known new moon, and the mean synodic month.
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
_SYNODIC_DAYS = 29.530588853


def moon_phase(when=None):
    """-> (illuminated fraction 0-1, phase name). Pure arithmetic, no network."""
    when = when or datetime.now(timezone.utc)
    if isinstance(when, date) and not isinstance(when, datetime):
        when = datetime(when.year, when.month, when.day, 12, tzinfo=timezone.utc)
    days = (when - _KNOWN_NEW_MOON).total_seconds() / 86400.0
    age = days % _SYNODIC_DAYS
    # Illumination follows the cosine of the phase angle.
    import math
    fraction = (1 - math.cos(2 * math.pi * age / _SYNODIC_DAYS)) / 2
    names = [(1.85, "new moon"), (5.5, "waxing crescent"), (9.2, "first quarter"),
             (12.9, "waxing gibbous"), (16.6, "full moon"), (20.3, "waning gibbous"),
             (23.9, "last quarter"), (27.7, "waning crescent"), (99, "new moon")]
    return fraction, next(n for limit, n in names if age < limit)


def get_stargazing_conditions(place=None, latitude=None, longitude=None):
    """Cloud, moonlight and darkness tonight — by default up at Las Cañadas."""
    if place or (latitude is not None and longitude is not None):
        lat, lon, where = resolve(place, latitude, longitude)
        if lat is None:
            return where
    else:
        lat, lon, where = TEIDE

    res = requests.get(FORECAST, params={
        "latitude": lat, "longitude": lon,
        "hourly": "cloud_cover,cloud_cover_low,cloud_cover_high,temperature_2m,wind_speed_10m",
        "daily": "sunset",
        "timezone": "Atlantic/Canary", "forecast_days": 1,
    }, timeout=10)
    res.raise_for_status()
    data = res.json()
    hourly, daily = data.get("hourly", {}), data.get("daily", {})

    # Astronomical dark is roughly an hour and a half after sunset here; sample 21:00-01:00.
    times = hourly.get("time", [])
    night = [i for i, t in enumerate(times) if t[11:13] in ("21", "22", "23", "00", "01")]
    if not night:
        return f"No forecast available for {where} tonight."

    def avg(field):
        vals = [hourly[field][i] for i in night if hourly.get(field) and hourly[field][i] is not None]
        return sum(vals) / len(vals) if vals else None

    cloud, cloud_high = avg("cloud_cover"), avg("cloud_cover_high")
    temp, wind = avg("temperature_2m"), avg("wind_speed_10m")
    fraction, phase = moon_phase()

    if cloud is None:
        verdict = "No cloud forecast available."
    elif cloud < 20:
        verdict = "Clear — a good night for it."
    elif cloud < 50:
        verdict = "Patchy cloud; worth a try, but no promises."
    else:
        verdict = "Mostly cloudy — not a night for the drive up."

    lines = [
        f"Stargazing at {where} tonight:",
        f"  Cloud 21:00-01:00: {cloud:.0f}% average"
        + (f" (high cloud {cloud_high:.0f}%)" if cloud_high is not None else ""),
        f"  Moon: {phase}, {fraction * 100:.0f}% illuminated"
        + ("  — bright enough to wash out faint stars" if fraction > 0.65 else
           "  — little moonlight to spoil it" if fraction < 0.25 else ""),
    ]
    if daily.get("sunset"):
        lines.append(f"  Sunset {daily['sunset'][0][11:16]}; properly dark about 1.5 hours later")
    if temp is not None:
        lines.append(f"  Overnight up there: about {temp:.0f}°C, wind {wind:.0f} km/h — "
                     "colder than the coast, take a coat")
    lines.append(f"  {verdict}")
    return "\n".join(lines)


TOOLS = {
    "get_stargazing_conditions": {
        "description": (
            "Whether tonight is good for stargazing in Tenerife — cloud cover, moon phase, and "
            "how cold it will be. Defaults to Las Cañadas del Teide, where people go and where "
            "the sky is above the coastal cloud. Pass a place name for somewhere else."
        ),
        "parameters": {"type": "object", "properties": dict(LOCATION_PARAMS), "required": []},
        "run": get_stargazing_conditions,
    },
}
