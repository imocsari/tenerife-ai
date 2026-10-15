# ingest/sync_health.py
# Run from the project folder:  python -m ingest.sync_health
#
# Loads the Cabildo de Tenerife's register of pharmacies, health centres, hospitals and
# dentists into Postgres. Official island-government open data, free and keyless.
#
# Loaded rather than fetched per question: it is a static file of ~1,400 rows that changes a
# few times a year, so downloading it on every question would be slow, rude to the portal, and
# would make the one question that matters most — someone needing a pharmacy — depend on a
# third-party server being up at that moment.

import csv
import io

import psycopg
import requests

from app import config

CKAN_PACKAGE = "centros-medicos-farmacias-y-servicios-sanitarios-en-tenerife"
CKAN_API = "https://datos.tenerife.es/ckan/api/3/action/package_show"
USER_AGENT = "TenerifeAI/1.0 (travel assistant; contact: hello@tenerinfo.app)"

SETUP_SQL = """
CREATE TABLE IF NOT EXISTS tenerife_health_services (
    id            bigserial PRIMARY KEY,
    kind          text NOT NULL,          -- farmacia, centro de salud, servicios hospitalarios...
    name          text NOT NULL,
    address       text,
    municipality  text,
    postcode      text,
    phone         text,
    website       text,
    latitude      double precision,
    longitude     double precision
);
CREATE INDEX IF NOT EXISTS health_kind_idx ON tenerife_health_services (kind);
CREATE INDEX IF NOT EXISTS health_pos_idx  ON tenerife_health_services (latitude, longitude);
ALTER TABLE tenerife_health_services ENABLE ROW LEVEL SECURITY;
"""


def _address(row):
    parts = [row.get("tipo_via_descripcion"), row.get("direccion_nombre_via")]
    street = " ".join(p for p in parts if p)
    number = row.get("direccion_numero")
    return f"{street} {number}".strip() if number else street


def _phone(raw):
    """The CSV writes phone numbers as floats, e.g. 922770539.0 — and uses 0 as a placeholder
    for 'none recorded', which printed as 'tel 0' until this dropped it."""
    raw = (raw or "").strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    return raw if raw and raw.strip("0") else None


def main():
    headers = {"User-Agent": USER_AGENT}
    pkg = requests.get(CKAN_API, params={"id": CKAN_PACKAGE}, headers=headers, timeout=60)
    pkg.raise_for_status()
    csv_url = next(r["url"] for r in pkg.json()["result"]["resources"] if r.get("format") == "CSV")

    print(f"Downloading {CKAN_PACKAGE} ...")
    text = requests.get(csv_url, headers=headers, timeout=120).content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    print(f"  {len(rows)} rows")

    with psycopg.connect(config.DATABASE_URL, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(SETUP_SQL)
            # Replaced wholesale: a pharmacy that has closed must disappear, not linger.
            cur.execute("TRUNCATE tenerife_health_services")
            written = 0
            with cur.copy("COPY tenerife_health_services "
                          "(kind, name, address, municipality, postcode, phone, website, "
                          "latitude, longitude) FROM STDIN") as copy:
                for r in rows:
                    try:
                        lat, lon = float(r["latitud"]), float(r["longitud"])
                    except (TypeError, ValueError):
                        continue    # without a position it cannot answer "near me"
                    copy.write_row((
                        (r.get("actividad_tipo") or "").strip(),
                        (r.get("nombre") or "").strip(),
                        _address(r), (r.get("municipio_nombre") or "").strip(),
                        (r.get("direccion_codigo_postal") or "").strip(),
                        _phone(r.get("telefono")), (r.get("web") or "").strip() or None,
                        lat, lon,
                    ))
                    written += 1
            print(f"  loaded {written}")
        conn.commit()
    print("Done.")


if __name__ == "__main__":
    main()
