# app/tools/fuel.py
# Petrol and diesel prices from the Spanish government's open fuel-price register.
# Free, no key. Every station in the province, updated through the day.
#
# Hire cars are close to universal in Tenerife and fuel here is far cheaper than mainland
# Europe, so "where do I fill up" is a real question — and prices between neighbouring
# stations differ enough to be worth a few minutes' detour.

import math

import requests

from app.tools._located import LOCATION_PARAMS, resolve

# 38 is the province code for Santa Cruz de Tenerife, which covers the whole island.
PROVINCE_URL = ("https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes"
                "/PreciosCarburantes/EstacionesTerrestres/FiltroProvincia/38")

FUELS = {
    "petrol": "Precio Gasolina 95 E5",
    "petrol98": "Precio Gasolina 98 E5",
    "diesel": "Precio Gasoleo A",
    "diesel_premium": "Precio Gasoleo Premium",
}


def _spanish_float(text):
    """The register writes 1,448 for 1.448 €/litre."""
    try:
        return float((text or "").replace(",", "."))
    except ValueError:
        return None


def get_fuel_prices(place=None, latitude=None, longitude=None, fuel="petrol", limit=5):
    """Cheapest filling stations near a place in Tenerife."""
    lat, lon, where = resolve(place, latitude, longitude)
    if lat is None:
        return where

    key = FUELS.get(fuel, FUELS["petrol"])
    res = requests.get(PROVINCE_URL, timeout=30)
    res.raise_for_status()

    nearby = []
    for s in res.json().get("ListaEESSPrecio", []):
        price = _spanish_float(s.get(key))
        slat = _spanish_float(s.get("Latitud"))
        slon = _spanish_float(s.get("Longitud (WGS84)"))
        if price is None or slat is None or slon is None:
            continue    # not every station sells every fuel; a blank price is normal
        km = math.dist((lat, lon * math.cos(math.radians(lat))),
                       (slat, slon * math.cos(math.radians(lat)))) * 111.32
        if km <= 15:
            nearby.append((price, km, s))

    if not nearby:
        return f"No filling stations with {fuel} prices found within 15km of {where}."

    nearby.sort(key=lambda t: t[0])
    lines = [f"Cheapest {fuel} within 15km of {where} (€/litre):"]
    for price, km, s in nearby[:max(1, min(int(limit), 10))]:
        lines.append(f"  €{price:.3f}  {s.get('Rótulo', '?').title()} — "
                     f"{s.get('Dirección', '').title()}, {s.get('Localidad', '').title()} "
                     f"({km:.1f} km)")
    lines.append("Source: Spanish government fuel-price register, updated through the day.")
    return "\n".join(lines)


TOOLS = {
    "get_fuel_prices": {
        "description": (
            "Cheapest petrol or diesel stations near a place in Tenerife, with live prices from "
            "the Spanish government register. fuel can be 'petrol', 'petrol98', 'diesel' or "
            "'diesel_premium'. Pass the place name; it finds the coordinates itself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                **LOCATION_PARAMS,
                "fuel": {"type": "string", "description": "petrol | petrol98 | diesel | diesel_premium"},
                "limit": {"type": "integer", "description": "How many stations to list (default 5)"},
            },
            "required": [],
        },
        "run": get_fuel_prices,
    },
}
