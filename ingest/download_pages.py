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
HEADERS = {"User-Agent": "tenerife-ai learning project (your-email@example.com)"}


def main():
    config.PAGES_DIR.mkdir(parents=True, exist_ok=True)

    for title in PAGES:
        params = {
            "action": "query", "prop": "extracts", "explaintext": 1,
            "titles": title, "format": "json", "formatversion": 2,
        }
        response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
        page = response.json()["query"]["pages"][0]

        if "missing" in page:
            print(f"Not found: {title}")
            continue

        path = config.PAGES_DIR / (title.replace(" ", "_") + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"title": title, "text": page["extract"]}, f, ensure_ascii=False, indent=2)
        print(f"Saved {title}: {len(page['extract'])} characters")


if __name__ == "__main__":
    main()
