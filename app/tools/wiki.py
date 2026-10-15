# app/tools/wiki.py
# Wikipedia lookup, as a last resort for places the guide does not cover.
#
# The Wikivoyage corpus is six towns. The island has hundreds of places people ask about —
# Masca, Anaga, Garachico, Icod's dragon tree, Candelaria — and for those the honest options
# are "I don't know" or a sourced encyclopaedia entry. This is the second.
#
# Deliberately last in the model's list of tools: TenerInfo's own data is current and local,
# Wikipedia is neither, and it must never be preferred for anything about what is on.

from functools import lru_cache

import requests

SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
SEARCH = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "TenerifeAI/1.0 (travel assistant; contact: hello@tenerinfo.app)"


@lru_cache(maxsize=128)
def _search_title(query):
    """Exact titles fail often — 'Masca, Tenerife' 404s while 'Masca' works — so search first."""
    res = requests.get(SEARCH, params={
        "action": "query", "list": "search", "srsearch": f"{query} Tenerife",
        "srlimit": 1, "format": "json", "formatversion": 2,
    }, headers={"User-Agent": USER_AGENT}, timeout=15)
    res.raise_for_status()
    hits = res.json().get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


@lru_cache(maxsize=128)
def look_up_place(name):
    """A short encyclopaedia summary of a place or landmark in Tenerife."""
    title = _search_title(name)
    if not title:
        return f"Wikipedia has nothing for {name!r}."

    res = requests.get(SUMMARY.format(title=title.replace(" ", "_")),
                       headers={"User-Agent": USER_AGENT}, timeout=15)
    if res.status_code != 200:
        return f"Wikipedia has nothing usable for {name!r}."
    data = res.json()
    extract = (data.get("extract") or "").strip()
    if not extract:
        return f"Wikipedia has an entry for {title!r} but no summary text."

    out = [f"{data.get('title', title)} (Wikipedia)", extract]
    page_url = (data.get("content_urls", {}).get("desktop", {}) or {}).get("page")
    if page_url:
        out.append(page_url)
    return "\n".join(out)


TOOLS = {
    "look_up_place": {
        "description": (
            "Background on a Tenerife place or landmark from Wikipedia — history, geography, "
            "what it is. LAST RESORT only: use search_tenerinfo first, and never use this for "
            "events, opening times, prices or anything that changes."
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string",
                                    "description": "Place or landmark, e.g. 'Masca', 'Drago Milenario'"}},
            "required": ["name"],
        },
        "run": look_up_place,
    },
}
