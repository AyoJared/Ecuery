"""Create the schema on a Tiger service and seed it with demo readings.

Run from backend/ after putting TIGER_DATABASE_URL in .env.local:
    python -m tiger.setup_db            # schema + 14 days of demo data
    python -m tiger.setup_db --days 30
    python -m tiger.setup_db --schema-only
Safe to re-run: everything is IF NOT EXISTS / ON CONFLICT DO NOTHING.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv

from .sample_data import generate

BACKEND = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).with_name("schema.sql")


def apply_schema(conn: psycopg.Connection) -> None:
    for statement in SCHEMA.read_text(encoding="utf-8").split(";"):
        body = "\n".join(l for l in statement.splitlines() if not l.strip().startswith("--")).strip()
        if body:
            conn.execute(body)
    print("schema: sensor_readings hypertable + readings_hourly / readings_daily ready")


def seed(conn: psycopg.Connection, days: int) -> None:
    end = datetime.now(timezone.utc)
    rows = generate(end - timedelta(days=days), end)
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE staging (LIKE sensor_readings) ON COMMIT DROP")
        with cur.copy("COPY staging (time, location, metric, value, unit, source) FROM STDIN") as copy:
            count = 0
            for row in rows:
                copy.write_row(row)
                count += 1
        cur.execute("INSERT INTO sensor_readings SELECT * FROM staging ON CONFLICT DO NOTHING")
        inserted = cur.rowcount
    conn.commit()
    print(f"seed: generated {count} readings, inserted {inserted} new")


def refresh(conn: psycopg.Connection) -> None:
    for view in ("readings_hourly", "readings_daily"):
        conn.execute(f"CALL refresh_continuous_aggregate('{view}', NULL, NULL)")
    print("aggregates: refreshed")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--schema-only", action="store_true")
    args = parser.parse_args()

    load_dotenv(BACKEND / ".env.local")
    url = os.getenv("TIGER_DATABASE_URL")
    if not url:
        sys.exit("TIGER_DATABASE_URL is not set. Run `tiger db uri` and add it to backend/.env.local.")
    if not urlparse(url).password and not os.getenv("PGPASSWORD"):
        sys.exit("TIGER_DATABASE_URL has no password. Put it in the URL (tsdbadmin:PASSWORD@host) "
                 "or add PGPASSWORD=... to backend/.env.local.")

    with psycopg.connect(url, autocommit=True) as conn:
        apply_schema(conn)
    if args.schema_only:
        return
    with psycopg.connect(url) as conn:
        seed(conn, args.days)
    with psycopg.connect(url, autocommit=True) as conn:
        refresh(conn)


if __name__ == "__main__":
    main()
