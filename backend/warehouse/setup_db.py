"""Create the Snowflake warehouse, database, tables and reader role, then load demo history.

Run from backend/ after putting SNOWFLAKE_* in .env.local:
    python -m warehouse.setup_db              # schema + history from 2019 up to the Tiger window
    python -m warehouse.setup_db --schema-only
Safe to re-run: demo rows are replaced, real data (other sources) is untouched.
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND / ".env.local")

import snowflake.connector  # noqa: E402

from .config import connect_params, is_configured  # noqa: E402
from .sample_data import HISTORY_START, SOURCE, generate_history  # noqa: E402

SCHEMA = Path(__file__).with_name("schema.sql")
BATCH = 5000


def connect():
    if not is_configured():
        sys.exit("Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and SNOWFLAKE_PRIVATE_KEY_FILE (or SNOWFLAKE_PASSWORD) "
                 "in backend/.env.local (see warehouse/README.md).")
    # No warehouse/database yet on first run, so connect without them.
    return snowflake.connector.connect(**connect_params(with_context=False))


def apply_schema(cur) -> None:
    for statement in SCHEMA.read_text(encoding="utf-8").split(";"):
        body = "\n".join(l for l in statement.splitlines() if not l.strip().startswith("--")).strip()
        if body:
            cur.execute(body)
    user = cur.execute("SELECT CURRENT_USER()").fetchone()[0]
    cur.execute(f'GRANT ROLE ECUERY_READER TO USER "{user}"')
    print(f"schema: ECUERY_WH, ECUERY.HISTORY.DAILY_READINGS, MONTHLY_READINGS, role ECUERY_READER (granted to {user})")


def seed(cur, recent_days: int) -> None:
    cur.execute("USE WAREHOUSE ECUERY_WH")
    cur.execute("USE SCHEMA ECUERY.HISTORY")
    cur.execute("DELETE FROM DAILY_READINGS WHERE SOURCE = %s", (SOURCE,))
    end = date.today() - timedelta(days=recent_days)
    sql = ("INSERT INTO DAILY_READINGS (DAY, LOCATION, METRIC, UNIT, AVG_VALUE, MIN_VALUE, MAX_VALUE, SAMPLES, SOURCE) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)")
    batch, total = [], 0
    for row in generate_history(HISTORY_START, end):
        batch.append(row)
        if len(batch) == BATCH:
            cur.executemany(sql, batch)
            total += len(batch)
            batch = []
            print(f"  loaded {total} rows...", end="\r")
    if batch:
        cur.executemany(sql, batch)
        total += len(batch)
    print(f"seed: loaded {total} daily rows, {HISTORY_START} to {end - timedelta(days=1)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--recent-days", type=int, default=int(os.getenv("RECENT_DAYS", "14")),
                        help="stop history this many days ago; Tiger holds the rest")
    args = parser.parse_args()

    with connect() as conn, conn.cursor() as cur:
        apply_schema(cur)
        if not args.schema_only:
            seed(cur, args.recent_days)


if __name__ == "__main__":
    main()
