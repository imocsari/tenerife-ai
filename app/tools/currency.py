# app/tools/currency.py
# Currency conversion from the European Central Bank's daily reference rates, via Frankfurter.
# Free, no key, no account.
#
# Worth a tool rather than letting the model answer from memory: an exchange rate it recalls
# from training is months stale and stated with total confidence, which is the one kind of
# wrong answer a visitor acts on immediately at a cash machine.

from functools import lru_cache
from datetime import date

import requests

FRANKFURTER = "https://api.frankfurter.app/latest"


@lru_cache(maxsize=64)
def _rate(base, target, _day):
    """_day is in the cache key so rates refresh daily without a manual flush."""
    res = requests.get(FRANKFURTER, params={"from": base, "to": target}, timeout=10)
    res.raise_for_status()
    data = res.json()
    return data["rates"].get(target), data.get("date")


def convert_currency(amount=1.0, from_currency="GBP", to_currency="EUR"):
    """Convert an amount between currencies at today's ECB reference rate."""
    base, target = from_currency.upper().strip(), to_currency.upper().strip()
    if base == target:
        return f"{amount} {base} is {amount} {target}."
    try:
        rate, as_of = _rate(base, target, date.today().isoformat())
    except requests.HTTPError:
        return f"Could not get a rate for {base} to {target} — check the currency codes."
    if rate is None:
        return f"No ECB rate available for {base} to {target}."
    return (f"{float(amount):,.2f} {base} = {float(amount) * rate:,.2f} {target}\n"
            f"(1 {base} = {rate:.4f} {target}, ECB reference rate for {as_of}. "
            "A bureau de change or card will give you a little less.)")


TOOLS = {
    "convert_currency": {
        "description": (
            "Convert money between currencies at the European Central Bank's daily rate. Use "
            "whenever someone asks what something costs in their own currency — never answer "
            "an exchange rate from memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "How much to convert (default 1)"},
                "from_currency": {"type": "string", "description": "ISO code, e.g. GBP, USD, SEK"},
                "to_currency": {"type": "string", "description": "ISO code, usually EUR here"},
            },
            "required": ["from_currency", "to_currency"],
        },
        "run": convert_currency,
    },
}
