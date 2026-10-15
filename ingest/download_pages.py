# ingest/download_pages.py
# Downloads Tenerife pages from Wikivoyage into data/pages/.
# Run from the project folder:  python -m ingest.download_pages

import json
import requests

from app import config

PAGES = [
    "Tenerife",
    "Los Cristianos",
    "Puerto de la Cruz",
    "Santa Cruz de Tenerife",
    "La Laguna",
    "Teide National Park",
]

API_URL = "https://en.wikivoyage.org/w/api.php"
# Wikimedia asks for a real contact in the User-Agent and throttles anonymous-looking ones.
HEADERS = {"User-Agent": "TenerifeAI/1.0 (travel assistant; contact: hello@tenerinfo.app)"}


def main():
    config.PAGES_DIR.mkdir(parents=True, exist_ok=True)

    for title in PAGES:
        params = {
            "action": "query", "prop": "extracts", "explaintext": 1,
            "titles": title, "format": "json", "formatversion": 2,
            # Follow redirects, e.g. "La Laguna" -> "San Cristóbal de La Laguna". Without this
            # the API returns the redirect stub itself: not flagged missing, just empty — which
            # is how La Laguna sat in the knowledge base as a 0-character page.
            "redirects": 1,
        }
        response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
        page = response.json()["query"]["pages"][0]

        if "missing" in page:
            print(f"Not found: {title}")
            continue

        # An empty extract is a failure, not a success. The old check only caught "missing",
        # so a page that resolved but carried no text was saved and counted as fine.
        text = page.get("extract") or ""
        if not text.strip():
            print(f"EMPTY, not saved: {title} — resolved to {page.get('title')!r} with no text")
            continue

        # Store the title the wiki actually used, so a redirected page is labelled by its real
        # name in every citation the assistant shows.
        resolved = page.get("title", title)
        path = config.PAGES_DIR / (resolved.replace(" ", "_") + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"title": resolved, "text": text}, f, ensure_ascii=False, indent=2)
        note = f" (redirected from {title})" if resolved != title else ""
        print(f"Saved {resolved}{note}: {len(text):,} characters")


if __name__ == "__main__":
    main()
