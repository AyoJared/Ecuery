"""Pull real data from EPA, NOAA and USGS into Tiger/Snowflake, with every batch anchored on Solana.

Run from backend/:
    python -m ingest.run --recent                 # last RECENT_DAYS days -> Tiger   (run hourly)
    python -m ingest.run --history                # 2019 -> recent cutoff -> Snowflake (run daily/weekly)
    python -m ingest.run --history --since 2023-01-01
    python -m ingest.run --all --drop-demo        # first run: load everything, remove the demo data
"""

import argparse
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from readings.service import recent_cutoff  # noqa: E402

from . import sources, store  # noqa: E402
from .commit import commit as commit_batch  # noqa: E402
from .provenance import Batch, anchor  # noqa: E402


def commit(batch: Batch) -> Batch:
    started = time.perf_counter()
    anchored = commit_batch(batch)
    if anchored is None:
        print(f"  - {batch.source:10} {batch.dataset}: no rows, skipped")
        return batch
    chain = anchored.get("signature") or f"NOT ANCHORED ({anchored.get('error')})"
    print(f"  ✓ {batch.source:10} {len(batch.rows):>6} rows, {len(batch.requests):>3} files -> {batch.store:9} "
          f"| {batch.batch_id} | solana {str(chain)[:20]}… | {time.perf_counter() - started:.1f}s")
    return batch


def run_step(label: str, fn):
    started = time.perf_counter()
    print(f"• {label}")
    try:
        batch = fn()
        print(f"    fetched in {time.perf_counter() - started:.1f}s")
        return commit(batch)
    except Exception as e:  # one agency being down shouldn't stop the others
        print(f"  ✗ {label} failed: {type(e).__name__}: {str(e)[:200]}")
        return None


def history(since: date) -> None:
    until = recent_cutoff().date()
    print(f"\nHISTORY -> Snowflake, {since} .. {until - timedelta(days=1)}")
    covered: set[tuple] = set()
    last_aqs: dict[tuple, date] = defaultdict(lambda: since - timedelta(days=1))
    for metric in ("pm25", "o3", "no2"):
        b = run_step(f"EPA AQS {metric}", lambda m=metric: sources.epa_aqs(m, since, until))
        for r in (b.rows if b else []):
            covered.add((r[1], r[2], r[0]))
            last_aqs[(r[1], r[2])] = max(last_aqs[(r[1], r[2])], r[0])
    # AQS lags by months; fill from the preliminary AirNow daily files where AQS has nothing yet.
    gap_start = min((d for (_, m), d in last_aqs.items() if m in ("pm25", "o3")), default=since - timedelta(days=1)) + timedelta(days=1)
    gap_start = max(gap_start, since)
    if gap_start < until:
        run_step(f"EPA AirNow daily gap fill {gap_start}..", lambda: sources.epa_airnow_daily(gap_start, until, covered))
    run_step("NOAA NCEI temperature", lambda: sources.noaa_ncei_temperature(since, until))
    run_step("NOAA NCEI humidity (GSOD)", lambda: sources.noaa_gsod_humidity(since, until))
    run_step("NOAA GML CO2", lambda: sources.noaa_gml_co2(since, until, "snowflake"))
    run_step("USGS daily streamflow / water temperature", lambda: sources.usgs_daily(since, until))


def recent() -> None:
    since, now = recent_cutoff(), datetime.now(timezone.utc)
    print(f"\nRECENT -> Tiger, {since:%Y-%m-%d %H:%M} .. now (UTC)")
    run_step("EPA AirNow hourly", lambda: sources.epa_airnow_hourly(since, now))
    run_step("NOAA NWS observations", lambda: sources.noaa_nws(max(since, now - timedelta(days=7))))
    run_step("USGS instantaneous values", lambda: sources.usgs_recent(since))
    run_step("NOAA GML CO2", lambda: sources.noaa_gml_co2(since.date(), now.date() + timedelta(days=1), "tiger"))
    store.refresh_aggregates()
    print("  ✓ Tiger continuous aggregates refreshed")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recent", action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--since", type=date.fromisoformat, default=date(2019, 1, 1))
    parser.add_argument("--drop-demo", action="store_true", help="delete the synthetic demo rows")
    parser.add_argument("--reanchor", action="store_true", help="anchor batches whose Solana write failed earlier")
    args = parser.parse_args()
    if not (args.recent or args.history or args.all or args.drop_demo or args.reanchor):
        parser.error("choose --recent, --history, --all, --drop-demo and/or --reanchor")

    store.ensure_schema()
    if args.drop_demo:
        print("Removed demo rows:", store.delete_demo_data())
    if args.history or args.all:
        history(args.since)
    if args.recent or args.all:
        recent()
    if args.reanchor:
        for row in store.unanchored():
            anchored = anchor(row["manifest"])
            store.set_anchor(row["batch_id"], anchored)
            print(f"  {row['batch_id']}: {anchored.get('signature') or anchored.get('error')}")


if __name__ == "__main__":
    main()
