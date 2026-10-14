# app/tools/holidays.py
# Spanish public holidays from Nager.Date. Free, no key.
#
# Worth a tool of its own because a holiday changes the answer to ordinary questions: shops and
# council offices shut, buses drop to a Sunday timetable, and the island's own days (Día de
# Canarias, and the local patron-saint fiestas) are not in most generic calendars. The API
# labels regional holidays by county code, so ES-CN entries are the Canary ones.

from functools import lru_cache
from datetime import date

import requests

NAGER = "https://date.nager.at/api/v3/PublicHolidays/{year}/ES"
CANARIES = "ES-CN"


@lru_cache(maxsize=8)
def _fetch(year):
    res = requests.get(NAGER.format(year=year), timeout=10)
    res.raise_for_status()
    return res.json()


def get_public_holidays(year=None, upcoming_only=True):
    """Spanish public holidays that apply in the Canary Islands."""
    year = int(year) if year else date.today().year
    try:
        holidays = _fetch(year)
    except requests.HTTPError:
        return f"No holiday data available for {year}."

    today = date.today().isoformat()
    out = []
    for h in holidays:
        counties = h.get("counties")
        # counties is null for nationwide holidays; a list when it is regional only.
        if counties and CANARIES not in counties:
            continue
        if upcoming_only and h["date"] < today:
            continue
        scope = "Canary Islands" if counties else "nationwide"
        out.append(f"  {h['date']}  {h['localName']} ({h['name']}) — {scope}")

    if not out:
        return f"No {'remaining ' if upcoming_only else ''}public holidays in {year}."
    header = f"Public holidays in the Canary Islands, {year}"
    if upcoming_only:
        header += " (from today)"
    return header + ":\n" + "\n".join(out)


TOOLS = {
    "get_public_holidays": {
        "description": (
            "Spanish public holidays that apply in the Canary Islands, including island-specific "
            "ones. Useful because shops, offices and bus timetables change on these days."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "Year, e.g. 2026 (default: this year)"},
                "upcoming_only": {"type": "boolean", "description": "Only holidays still to come (default true)"},
            },
            "required": [],
        },
        "run": get_public_holidays,
    },
}
