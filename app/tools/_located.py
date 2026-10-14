# app/tools/_located.py
# Shared "place name OR coordinates" resolution.
#
# Every outdoors tool needs a point on the map, and small models cannot reliably chain
# geocode_place -> the tool (2026-10-14: qwen2.5:7b fetched coordinates then told the user to
# look up the weather themselves). So each tool accepts a place name and resolves it here,
# rather than each one re-implementing the same two-step dance.

def resolve(place=None, latitude=None, longitude=None):
    """-> (latitude, longitude, label) or (None, None, message_for_the_model)."""
    if latitude is not None and longitude is not None:
        return float(latitude), float(longitude), f"{float(latitude):.4f}, {float(longitude):.4f}"
    if not place:
        return None, None, "Give me either a place name or both latitude and longitude."

    from app.tools.geocode import geocode_place
    located = geocode_place(place)
    try:
        lat = float([l for l in located.splitlines() if l.startswith("latitude")][0].split(": ")[1])
        lon = float([l for l in located.splitlines() if l.startswith("longitude")][0].split(": ")[1])
    except (IndexError, ValueError):
        return None, None, located          # the geocoder's own "no such place" message
    return lat, lon, located.splitlines()[0]


LOCATION_PARAMS = {
    "place": {"type": "string", "description": "Place name, e.g. 'Los Gigantes'"},
    "latitude": {"type": "number", "description": "Latitude, if already known"},
    "longitude": {"type": "number", "description": "Longitude, if already known"},
}
