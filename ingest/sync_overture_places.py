# ingest/sync_overture_places.py
# Run from the project folder:  python -m ingest.sync_overture_places
#
# Everyday places for Tenerife — nail bars, hairdressers, supermarkets, launderettes, ATMs,
# viewpoints and the rest — from Overture Maps, loaded into Postgres.
#
# Why Overture and not OpenStreetMap's Overpass API, which was tried first (2026-10-15):
#
#   Reliability  Overpass returned 502, then 200 after 28.6s, then 502 again within a minute,
#                and a bulk load died after six retries across three public mirrors having
#                fetched two rows. Overture is static Parquet on S3 — nothing to overload.
#   Coverage     36,020 places in the Tenerife bounding box, with names, categories,
#                addresses and phone numbers.
#   Licence      Overture Places is CDLA-Permissive-2.0: attribution, no share-alike. OSM is
#                ODbL, whose share-alike obligation reaches derived databases — a real
#                consideration for anything commercial built on top of this.
#
# DuckDB reads the Parquet directly over HTTPS and pushes the bounding box down, so only the
# relevant row groups are fetched rather than the global dataset.

import duckdb
import psycopg

from app import config

# Pin the release rather than tracking "latest": a monthly drop should be a deliberate upgrade,
# not something that silently changes what the assistant says. Check for newer ones at
# https://overturemaps-us-west-2.s3.amazonaws.com/?list-type=2&prefix=release/&delimiter=/
RELEASE = "2026-09-23.1"
SOURCE = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*"

# Tenerife, with a little margin.
BBOX = (-16.96, 27.99, -16.10, 28.60)   # west, south, east, north

# Overture's own taxonomy values. Everyday needs that TenerInfo's venue data does not cover —
# it knows bars, restaurants and nightlife; it does not know where to get your nails done or
# find a launderette.
WANTED = (
    "nail_salon", "beauty_salon", "hair_salon", "barber", "spa", "massage",
    "supermarket", "grocery_store", "bakery", "butcher", "laundry", "dry_cleaning",
    "atm", "bank", "post_office", "car_rental", "car_wash", "gas_station",
    "shopping_center", "market", "tourist_information", "viewpoint",
    "gym", "golf_course", "playground", "library", "cinema", "museum",
)

SETUP_SQL = """
CREATE TABLE IF NOT EXISTS overture_places (
    id          text PRIMARY KEY,
    category    text NOT NULL,
    name        text NOT NULL,
    locality    text,
    address     text,
    postcode    text,
    phone       text,
    website     text,
    confidence  double precision,
    latitude    double precision NOT NULL,
    longitude   double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS overture_category_idx ON overture_places (category);
CREATE INDEX IF NOT EXISTS overture_pos_idx      ON overture_places (latitude, longitude);
CREATE INDEX IF NOT EXISTS overture_name_idx     ON overture_places (lower(name));
ALTER TABLE overture_places ENABLE ROW LEVEL SECURITY;
"""


def fetch():
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    west, south, east, north = BBOX
    categories = ", ".join(f"'{c}'" for c in WANTED)
    # operating_status filters out places Overture already knows have closed.
    return con.execute(f"""
        SELECT id,
               taxonomy.primary                AS category,
               names.primary                   AS name,
               addresses[1].locality           AS locality,
               addresses[1].freeform           AS address,
               addresses[1].postcode           AS postcode,
               phones[1]                       AS phone,
               websites[1]                     AS website,
               confidence,
               (bbox.ymin + bbox.ymax) / 2     AS latitude,
               (bbox.xmin + bbox.xmax) / 2     AS longitude
        FROM read_parquet('{SOURCE}')
        WHERE bbox.xmin BETWEEN {west} AND {east}
          AND bbox.ymin BETWEEN {south} AND {north}
          AND taxonomy.primary IN ({categories})
          AND names.primary IS NOT NULL
          AND (operating_status IS NULL OR operating_status <> 'closed')
    """).fetchall()


def main():
    print(f"Reading Overture {RELEASE} for Tenerife (this pulls remote Parquet, allow a minute)...")
    rows = fetch()
    print(f"  {len(rows):,} places")

    with psycopg.connect(config.DATABASE_URL, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(SETUP_SQL)
            # Replaced wholesale: a salon that has closed must disappear, not linger.
            cur.execute("TRUNCATE overture_places")
            with cur.copy("COPY overture_places (id, category, name, locality, address, "
                          "postcode, phone, website, confidence, latitude, longitude) "
                          "FROM STDIN") as copy:
                for r in rows:
                    copy.write_row(r)
        conn.commit()

    from collections import Counter
    for category, n in Counter(r[1] for r in rows).most_common(8):
        print(f"    {n:>5}  {category}")
    print("Done. Data © Overture Maps Foundation, CDLA-Permissive-2.0.")


if __name__ == "__main__":
    main()
