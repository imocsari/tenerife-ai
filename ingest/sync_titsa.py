# ingest/sync_titsa.py
# Run from the project folder:  python -m ingest.sync_titsa
#
# Loads TITSA's bus timetable (GTFS) into Postgres so the assistant can answer "when is the
# next bus from Los Cristianos to Costa Adeje" from the real schedule rather than guesswork.
#
# Three things about this feed drove the design:
#
# 1. titsa.com returns 403 to anything without a browser User-Agent. The file is public; it
#    just refuses non-browser clients.
# 2. 33,623 departures are at hour 24 or later (up to 30:00). That is legal GTFS — it means
#    "after midnight, still counted as the previous service day" — and it is why times are
#    stored as text plus seconds-since-midnight rather than as a SQL `time`, which would
#    reject or silently wrap them.
# 3. There is no calendar.txt, only calendar_dates.txt, so a service runs on exactly the dates
#    listed with exception_type 1. No weekday patterns to interpret.
#
# shapes.txt (775,517 rows, 30MB) is deliberately skipped: it is the drawn line of each route
# on a map, and answers no timetable question.

import csv
import io
import zipfile
from pathlib import Path

import psycopg
import requests

from app import config

GTFS_URL = "https://www.titsa.com/Google_transit.zip"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)

SETUP_SQL = """
CREATE TABLE IF NOT EXISTS titsa_stops (
    stop_id text PRIMARY KEY, stop_name text NOT NULL,
    latitude double precision, longitude double precision);

CREATE TABLE IF NOT EXISTS titsa_routes (
    route_id text PRIMARY KEY, short_name text, long_name text);

CREATE TABLE IF NOT EXISTS titsa_trips (
    trip_id text PRIMARY KEY, route_id text, service_id text, headsign text);

-- departure_seconds, not a time column: GTFS hours run past 24 for after-midnight services.
CREATE TABLE IF NOT EXISTS titsa_stop_times (
    trip_id text NOT NULL, stop_id text NOT NULL, stop_sequence integer NOT NULL,
    departure_text text, departure_seconds integer,
    PRIMARY KEY (trip_id, stop_sequence));

CREATE TABLE IF NOT EXISTS titsa_calendar_dates (
    service_id text NOT NULL, service_date date NOT NULL, exception_type integer,
    PRIMARY KEY (service_id, service_date));

CREATE INDEX IF NOT EXISTS titsa_stop_times_stop_idx ON titsa_stop_times (stop_id, departure_seconds);
CREATE INDEX IF NOT EXISTS titsa_stop_times_trip_idx ON titsa_stop_times (trip_id);
CREATE INDEX IF NOT EXISTS titsa_calendar_date_idx   ON titsa_calendar_dates (service_date, service_id);
CREATE INDEX IF NOT EXISTS titsa_stops_name_idx      ON titsa_stops (lower(stop_name));

ALTER TABLE titsa_stops           ENABLE ROW LEVEL SECURITY;
ALTER TABLE titsa_routes          ENABLE ROW LEVEL SECURITY;
ALTER TABLE titsa_trips           ENABLE ROW LEVEL SECURITY;
ALTER TABLE titsa_stop_times      ENABLE ROW LEVEL SECURITY;
ALTER TABLE titsa_calendar_dates  ENABLE ROW LEVEL SECURITY;
"""


def seconds(hhmmss):
    """'25:30:00' -> 91800. Hours past 24 are normal GTFS, not an error."""
    try:
        h, m, s = (int(p) for p in hhmmss.split(":"))
    except (ValueError, AttributeError):
        return None
    return h * 3600 + m * 60 + s


def read(zf, name):
    """GTFS files are UTF-8 with a BOM on the first header; strip it or the first column
    name comes back as '\\ufeffstop_id' and every lookup by that key misses."""
    with zf.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        yield from csv.DictReader(text)


def copy_rows(cur, table, columns, rows):
    """Bulk load. 1.3M stop_times through individual INSERTs would take hours; COPY takes
    seconds, and is the reason this is practical to re-run whenever the timetable changes."""
    written = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
            written += 1
    return written


def main():
    print(f"Downloading {GTFS_URL} ...")
    res = requests.get(GTFS_URL, headers={"User-Agent": USER_AGENT}, timeout=120)
    res.raise_for_status()
    print(f"  {len(res.content) / 1_000_000:.1f} MB")

    zf = zipfile.ZipFile(io.BytesIO(res.content))

    with psycopg.connect(config.DATABASE_URL, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(SETUP_SQL)

            # Replaced wholesale rather than upserted: a timetable change can withdraw trips,
            # and a left-behind row would have the assistant promising a bus that no longer runs.
            for table in ("titsa_stop_times", "titsa_trips", "titsa_calendar_dates",
                          "titsa_routes", "titsa_stops"):
                cur.execute(f"TRUNCATE {table}")

            n = copy_rows(cur, "titsa_stops", ["stop_id", "stop_name", "latitude", "longitude"],
                          ((r["stop_id"], r["stop_name"], r.get("stop_lat") or None,
                            r.get("stop_lon") or None) for r in read(zf, "stops.txt")))
            print(f"  stops          {n:>9,}")

            n = copy_rows(cur, "titsa_routes", ["route_id", "short_name", "long_name"],
                          ((r["route_id"], r.get("route_short_name"), r.get("route_long_name"))
                           for r in read(zf, "routes.txt")))
            print(f"  routes         {n:>9,}")

            n = copy_rows(cur, "titsa_trips", ["trip_id", "route_id", "service_id", "headsign"],
                          ((r["trip_id"], r["route_id"], r["service_id"], r.get("trip_headsign"))
                           for r in read(zf, "trips.txt")))
            print(f"  trips          {n:>9,}")

            n = copy_rows(cur, "titsa_calendar_dates", ["service_id", "service_date", "exception_type"],
                          ((r["service_id"],
                            f'{r["date"][:4]}-{r["date"][4:6]}-{r["date"][6:]}',
                            int(r.get("exception_type") or 1)) for r in read(zf, "calendar_dates.txt")))
            print(f"  calendar_dates {n:>9,}")

            n = copy_rows(cur, "titsa_stop_times",
                          ["trip_id", "stop_id", "stop_sequence", "departure_text", "departure_seconds"],
                          ((r["trip_id"], r["stop_id"], int(r["stop_sequence"]),
                            r.get("departure_time"), seconds(r.get("departure_time")))
                           for r in read(zf, "stop_times.txt")))
            print(f"  stop_times     {n:>9,}")

            cur.execute("ANALYZE titsa_stop_times")
        conn.commit()
    print("Done.")


if __name__ == "__main__":
    main()
