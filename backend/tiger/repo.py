"""Step 3c: "Recent results" — query readings from Tiger Data.

PostgresTigerRepo talks to a real Tiger service when TIGER_DATABASE_URL is
set (get it with `tiger db uri`). Otherwise MockTigerRepo serves the same
synthetic data from memory so the API and MCP tools work without a database.
Both return the same shapes, so callers (router, MCP server, Gemini) never
need to know which one is active.
"""

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol

from .sample_data import LOCATIONS, METRICS, floor_to_step, generate
from shared.catalog import unit as metric_unit
from shared.series import DataUnavailable, json_safe, make_point, make_result, parse_time
from shared.sql_guard import check_readonly

Granularity = Literal["auto", "raw", "hourly", "daily"]

SCHEMA_DESCRIPTION = """\
Tiger Data (TimescaleDB / Postgres). All times are TIMESTAMPTZ in UTC.

sensor_readings (hypertable, raw 15-minute readings)
  time TIMESTAMPTZ, location TEXT, metric TEXT, value DOUBLE PRECISION, unit TEXT, source TEXT

readings_hourly / readings_daily (continuous aggregates of sensor_readings)
  bucket TIMESTAMPTZ, location TEXT, metric TEXT, unit TEXT,
  avg_value DOUBLE PRECISION, min_value DOUBLE PRECISION, max_value DOUBLE PRECISION, samples BIGINT

metric values: pm25 (µg/m³), o3 (ppb), no2 (ppb), temperature (°C), humidity (%), streamflow (ft³/s),
  water_temperature (°C), co2 (ppm, only at location 'global' = NOAA Mauna Loa)
location values: philadelphia, new_york, pittsburgh, baltimore, global
source / batch_id: which agency feed and which provenance batch (anchored on Solana) each row came from
Prefer readings_hourly / readings_daily for anything longer than a day.
Use time_bucket('1 hour', time) for custom bucketing and now() - INTERVAL '...' for ranges.
"""


class TigerRepo(Protocol):
    mode: str

    def list_metrics(self) -> list[dict]: ...

    def list_locations(self) -> list[str]: ...

    def recent(self, metric: str, location: str, start: datetime, end: datetime,
               granularity: Granularity = "auto") -> dict: ...

    def run_readonly_sql(self, sql: str, limit: int = 200) -> dict: ...


class TigerUnavailable(DataUnavailable):
    pass


MAX_HOURS = 24 * 90  # "recent" data; older questions route to Snowflake


def resolve_window(hours: float = 24, start: str | None = None, end: str | None = None) -> tuple[datetime, datetime]:
    """Turn either `hours` back from now, or explicit ISO start/end, into a UTC window."""
    end_dt = parse_time(end) if end else datetime.now(timezone.utc)
    start_dt = parse_time(start) if start else end_dt - timedelta(hours=min(hours, MAX_HOURS))
    if start_dt >= end_dt:
        raise ValueError("start must be before end")
    return start_dt, end_dt


def pick_granularity(start: datetime, end: datetime, granularity: Granularity) -> str:
    if granularity != "auto":
        return granularity
    span = end - start
    if span <= timedelta(days=2):
        return "raw"
    return "hourly" if span <= timedelta(days=31) else "daily"


class PostgresTigerRepo:
    mode = "tiger"

    def __init__(self, url: str):
        self.url = url

    def _connect(self, **kwargs):
        import psycopg
        from psycopg.rows import dict_row
        try:
            return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10, **kwargs)
        except psycopg.OperationalError as e:
            reason = str(e).splitlines()[0]
            if "no password supplied" in reason:
                reason = "TIGER_DATABASE_URL has no password; add it to the URL or set PGPASSWORD in .env.local"
            raise TigerUnavailable(f"Can't reach Tiger: {reason}") from None

    def list_metrics(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT metric, unit FROM readings_daily ORDER BY metric").fetchall()
        return [dict(r) for r in rows]

    def list_locations(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT location FROM readings_daily ORDER BY location").fetchall()
        return [r["location"] for r in rows]

    def recent(self, metric, location, start, end, granularity="auto") -> dict:
        g = pick_granularity(start, end, granularity)
        if g == "raw":
            sql = """SELECT time, value AS avg_value, value AS min_value, value AS max_value,
                            1 AS samples, unit
                     FROM sensor_readings
                     WHERE metric = %s AND location = %s AND time >= %s AND time < %s
                     ORDER BY time"""
        else:
            sql = f"""SELECT bucket AS time, avg_value, min_value, max_value, samples, unit
                      FROM readings_{g}
                      WHERE metric = %s AND location = %s AND bucket >= %s AND bucket < %s
                      ORDER BY bucket"""
        with self._connect() as conn:
            rows = conn.execute(sql, (metric, location, start, end)).fetchall()
            points = [make_point(r["time"], r["avg_value"], r["min_value"], r["max_value"], r["samples"]) for r in rows]
            batches = conn.execute(
                "SELECT DISTINCT source, batch_id FROM sensor_readings WHERE metric = %s AND location = %s "
                "AND time >= %s AND time < %s AND batch_id IS NOT NULL", (metric, location, start, end)).fetchall()
        unit = rows[0]["unit"] if rows else metric_unit(metric)
        return make_result(metric, location, unit, g, start, end, points, batches=[dict(b) for b in batches])

    def run_readonly_sql(self, sql: str, limit: int = 200) -> dict:
        statement = check_readonly(sql)
        with self._connect() as conn:
            conn.read_only = True  # Postgres rejects any write in this transaction
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute(statement)
                columns = [c.name for c in cur.description or []]
                rows = cur.fetchmany(limit + 1)
            conn.rollback()
        return {
            "columns": columns,
            "rows": [{k: json_safe(v) for k, v in r.items()} for r in rows[:limit]],
            "truncated": len(rows) > limit,
        }


class MockTigerRepo:
    mode = "mock"

    def __init__(self, days: int = 14):
        end = floor_to_step(datetime.now(timezone.utc))
        self._series: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)
        for t, location, metric, value, _unit, _src in generate(end - timedelta(days=days), end):
            self._series[(location, metric)].append((t, value))

    def list_metrics(self) -> list[dict]:
        return [{"metric": m, "unit": spec[0]} for m, spec in sorted(METRICS.items())]

    def list_locations(self) -> list[str]:
        return sorted(LOCATIONS)

    def recent(self, metric, location, start, end, granularity="auto") -> dict:
        g = pick_granularity(start, end, granularity)
        rows = [(t, v) for t, v in self._series.get((location, metric), []) if start <= t < end]
        if g == "raw":
            points = [make_point(t, v, v, v, 1) for t, v in rows]
        else:
            buckets: dict[datetime, list[float]] = defaultdict(list)
            for t, v in rows:
                key = t.replace(minute=0) if g == "hourly" else t.replace(hour=0, minute=0)
                buckets[key].append(v)
            points = [make_point(k, sum(vs) / len(vs), min(vs), max(vs), len(vs)) for k, vs in sorted(buckets.items())]
        return make_result(metric, location, metric_unit(metric), g, start, end, points, batches=[])

    def run_readonly_sql(self, sql: str, limit: int = 200) -> dict:
        check_readonly(sql)  # still validate, so the guard can be demoed without a DB
        raise TigerUnavailable("Raw SQL needs a real Tiger service. Set TIGER_DATABASE_URL (see tiger/README.md).")


_repo: TigerRepo | None = None


def get_repo() -> TigerRepo:
    global _repo
    if _repo is None:
        url = os.getenv("TIGER_DATABASE_URL")
        _repo = PostgresTigerRepo(url) if url else MockTigerRepo()
    return _repo
