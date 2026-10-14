# download_pages.py
# Downloads the Tenerife pages from Wikivoyage and saves each one as a text file.

import json
import os
import requests

# The pages we want. Add more names here later.
PAGES = [
    "Tenerife",
    "Los Cristianos",
    "Puerto de la Cruz",
    "Santa Cruz de Tenerife",
    "La Laguna",
    "Teide National Park",
]

API_URL = "https://en.wikivoyage.org/w/api.php"

# Wikipedia/Wikivoyage
HEADERS = {"User-Agent": "tenerife-ai (martinomocsari@gmail.com)"}

os.makedirs("data", exist_ok=True)  # create a "data" folder if it doesn't exist

for title in PAGES:
    params = {
        "action": "query",
        "prop": "extracts",    # give me the page text...
        "explaintext": 1,      # ...as plain text, not HTML
        "titles": title,
        "format": "json",
        "formatversion": 2,
    }
    response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
    page = response.json()["query"]["pages"][0]

    if "missing" in page:
        print(f"Not found: {title}")
        continue

    text = page["extract"]
    filename = "data/" + title.replace(" ", "_") + ".json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({"title": title, "text": text}, f, ensure_ascii=False, indent=2)

    print(f"Saved {title}: {len(text)} characters")
