"""Step 4: "Historical results" — query years of daily readings from Snowflake.

SnowflakeRepo connects when SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PASSWORD
are set. Otherwise MockWarehouseRepo serves the same synthetic history from
memory. Results use the shared series shape (shared/series.py), same as Tiger.
"""

import os
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Protocol

from shared.catalog import unit as metric_unit
from shared.series import DataUnavailable, error_text, json_safe, make_point, make_result
from shared.sql_guard import check_readonly
from tiger.sample_data import LOCATIONS, METRICS

from .config import connect_params, is_configured
from .sample_data import HISTORY_START, generate_history

Granularity = Literal["auto", "daily", "monthly", "yearly"]

SCHEMA_DESCRIPTION = """\
Snowflake (database ECUERY, schema HISTORY). Historical daily data going back years.

DAILY_READINGS (one row per day, location, metric)
  DAY DATE, LOCATION VARCHAR, METRIC VARCHAR, UNIT VARCHAR,
  AVG_VALUE FLOAT, MIN_VALUE FLOAT, MAX_VALUE FLOAT, SAMPLES INTEGER, SOURCE VARCHAR

MONTHLY_READINGS (view over DAILY_READINGS)
  MONTH DATE, LOCATION, METRIC, UNIT, AVG_VALUE, MIN_VALUE, MAX_VALUE, SAMPLES

metric values: pm25 (µg/m³), o3 (ppb), no2 (ppb), temperature (°C), humidity (%), streamflow (ft³/s),
  water_temperature (°C), co2 (ppm, only at location 'global' = NOAA Mauna Loa)
location values: philadelphia, new_york, pittsburgh, baltimore, global
SOURCE / BATCH_ID: which agency feed and which provenance batch (anchored on Solana) each row came from
Snowflake SQL: DATE_TRUNC('year', DAY), DATEADD(year, -5, CURRENT_DATE()), YEAR(DAY), MONTH(DAY).
"""


class WarehouseUnavailable(DataUnavailable):
    pass


class WarehouseRepo(Protocol):
    mode: str

    def list_metrics(self) -> list[dict]: ...

    def list_locations(self) -> list[str]: ...

    def coverage(self) -> dict: ...

    def history(self, metric: str, location: str, start: datetime, end: datetime,
                granularity: Granularity = "auto") -> dict: ...

    def run_readonly_sql(self, sql: str, limit: int = 200) -> dict: ...


def pick_granularity(start: datetime, end: datetime, granularity: Granularity) -> str:
    if granularity != "auto":
        return granularity
    span = end - start
    if span <= timedelta(days=120):
        return "daily"
    return "monthly" if span <= timedelta(days=365 * 6) else "yearly"


def day_range(start: datetime, end: datetime) -> tuple[date, date]:
    """Whole days touched by [start, end): first day, and the exclusive last day."""
    last = end.date() if end.time() == datetime.min.time() else end.date() + timedelta(days=1)
    return start.date(), last


def _bucket(d: date, g: str) -> date:
    if g == "monthly":
        return d.replace(day=1)
    if g == "yearly":
        return d.replace(month=1, day=1)
    return d


class SnowflakeRepo:
    mode = "snowflake"

    def __init__(self):
        self.reader_role = os.getenv("SNOWFLAKE_READER_ROLE", "ECUERY_READER")
        self._conns: dict[str, object] = {}
        self._lock = threading.Lock()

    def _conn(self, reader: bool = False):
        import snowflake.connector

        key = "reader" if reader else "main"
        with self._lock:
            conn = self._conns.get(key)
            if conn is None or conn.is_closed():
                try:
                    conn = snowflake.connector.connect(
                        **connect_params(role=self.reader_role if reader else None),
                        client_session_keep_alive=True,
                        session_parameters={"STATEMENT_TIMEOUT_IN_SECONDS": 20 if reader else 60,
                                            "QUERY_TAG": "ecuery"},
                    )
                except snowflake.connector.errors.Error as e:
                    raise WarehouseUnavailable(f"Can't reach Snowflake: {error_text(e)}") from None
                if reader:
                    self._lock_down(conn)
                self._conns[key] = conn
            return conn

    def _lock_down(self, conn) -> None:
        # Users get DEFAULT_SECONDARY_ROLES = ('ALL') by default, which silently adds every other role
        # the user has (e.g. ACCOUNTADMIN) to this session. Turn that off, and refuse to run if we can't.
        cur = conn.cursor()
        try:
            cur.execute("USE SECONDARY ROLES NONE")
            primary, secondary = cur.execute("SELECT CURRENT_ROLE(), CURRENT_SECONDARY_ROLES()").fetchone()
        finally:
            cur.close()
        if primary != self.reader_role or '"roles":""' not in secondary.replace(" ", ""):
            conn.close()
            raise WarehouseUnavailable(
                f"Refusing to run SQL: session is {primary} with secondary roles {secondary}, not {self.reader_role} alone")

    def _query(self, sql: str, params: tuple = (), reader: bool = False, limit: int | None = None):
        import snowflake.connector
        from snowflake.connector import DictCursor

        try:
            cur = self._conn(reader).cursor(DictCursor)
            try:
                cur.execute(sql, params)
                columns = [c.name.lower() for c in cur.description or []]
                rows = cur.fetchmany(limit) if limit else cur.fetchall()
            finally:
                cur.close()
        except snowflake.connector.errors.ProgrammingError:
            raise
        except snowflake.connector.errors.Error as e:
            raise WarehouseUnavailable(f"Snowflake error: {error_text(e)}") from None
        return columns, [{k.lower(): v for k, v in r.items()} for r in rows]

    def _safe_query(self, sql: str, params: tuple = ()):
        import snowflake.connector

        try:
            return self._query(sql, params)[1]
        except snowflake.connector.errors.ProgrammingError as e:
            hint = " (run `python -m warehouse.setup_db`?)" if "does not exist" in str(e) else ""
            raise WarehouseUnavailable(f"Snowflake query failed: {error_text(e)}{hint}") from None

    def list_metrics(self) -> list[dict]:
        return self._safe_query("SELECT DISTINCT METRIC, UNIT FROM DAILY_READINGS ORDER BY METRIC")

    def list_locations(self) -> list[str]:
        return [r["location"] for r in self._safe_query("SELECT DISTINCT LOCATION FROM DAILY_READINGS ORDER BY LOCATION")]

    def coverage(self) -> dict:
        row = self._safe_query("SELECT MIN(DAY) AS FIRST_DAY, MAX(DAY) AS LAST_DAY, COUNT(*) AS ROW_COUNT FROM DAILY_READINGS")[0]
        return {k: json_safe(v) for k, v in row.items()}

    def history(self, metric, location, start, end, granularity="auto") -> dict:
        g = pick_granularity(start, end, granularity)
        part = {"daily": "day", "monthly": "month", "yearly": "year"}[g]
        first, last = day_range(start, end)
        rows = self._safe_query(
            f"""SELECT DATE_TRUNC('{part}', DAY) AS T, AVG(AVG_VALUE) AS AVG_VALUE, MIN(MIN_VALUE) AS MIN_VALUE,
                       MAX(MAX_VALUE) AS MAX_VALUE, SUM(SAMPLES) AS SAMPLES, ANY_VALUE(UNIT) AS UNIT
                FROM DAILY_READINGS
                WHERE METRIC = %s AND LOCATION = %s AND DAY >= %s AND DAY < %s
                GROUP BY 1 ORDER BY 1""",
            (metric, location, first, last),
        )
        points = [make_point(r["t"], r["avg_value"], r["min_value"], r["max_value"], r["samples"]) for r in rows]
        batches = self._safe_query(
            "SELECT DISTINCT SOURCE, BATCH_ID FROM DAILY_READINGS WHERE METRIC = %s AND LOCATION = %s "
            "AND DAY >= %s AND DAY < %s AND BATCH_ID IS NOT NULL", (metric, location, first, last))
        unit = rows[0]["unit"] if rows else metric_unit(metric)
        return make_result(metric, location, unit, g, start, end, points, batches=batches)

    def run_readonly_sql(self, sql: str, limit: int = 200) -> dict:
        statement = check_readonly(sql)
        # Runs as the read-only role (see schema.sql), so Snowflake itself rejects writes.
        columns, rows = self._query(statement, reader=True, limit=limit + 1)
        return {
            "columns": columns,
            "rows": [{k: json_safe(v) for k, v in r.items()} for r in rows[:limit]],
            "truncated": len(rows) > limit,
        }


# Days that matter per metric: (column compared, threshold, description). Standard reference levels:
# EPA/WHO daily PM2.5, the 8-hour ozone standard, the ETCCDI "very heavy precipitation" index (R20mm),
# a common heat threshold for daily maximum temperature, and a CAMS dust-episode level.
THRESHOLDS = {
    "pm25": ("AVG_VALUE", 35.0, "days with average PM2.5 above 35 µg/m³"),
    "o3": ("MAX_VALUE", 70.0, "days with ozone above 70 ppb"),
    "dust": ("AVG_VALUE", 25.0, "days with average dust above 25 µg/m³ (a dust episode)"),
    "precipitation": ("AVG_VALUE", 20.0, "days with 20 mm of rain or more"),
    "temperature": ("MAX_VALUE", 35.0, "days reaching 35 °C"),
}


def yearly_stats(repo, metric: str, location: str, start, end) -> list[dict]:
    """Per year: mean, most extreme day, number of days/records and days past the metric's threshold."""
    column, threshold, _ = THRESHOLDS.get(metric, ("AVG_VALUE", None, None))
    above = f"COUNT_IF({column} >= {float(threshold)})" if threshold is not None else "NULL"
    first, last = day_range(start, end)
    rows = repo._safe_query(
        f"""SELECT YEAR(DAY) AS Y, AVG(AVG_VALUE) AS MEAN, MAX(MAX_VALUE) AS HIGHEST, MIN(MIN_VALUE) AS LOWEST,
                   COUNT(*) AS RECORDS, {above} AS ABOVE, MIN(DAY) AS FIRST_DAY, MAX(DAY) AS LAST_DAY
            FROM DAILY_READINGS WHERE METRIC = %s AND LOCATION = %s AND DAY >= %s AND DAY < %s
            GROUP BY 1 ORDER BY 1""", (metric, location, first, last))
    return [{"year": int(r["y"]), "mean": round(float(r["mean"]), 2), "highest": round(float(r["highest"]), 2),
             "lowest": round(float(r["lowest"]), 2), "records": int(r["records"]),
             "complete": r["first_day"].month == 1 and r["first_day"].day <= 31 and r["last_day"].month == 12,
             **({"days_above_threshold": int(r["above"])} if r["above"] is not None else {})} for r in rows]


class MockWarehouseRepo:
    mode = "mock"

    def __init__(self, recent_days: int = 14):
        self.last_day = date.today() - timedelta(days=recent_days)
        self._series: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        for d, location, metric, _unit, avg, lo, hi, samples, _src in generate_history(HISTORY_START, self.last_day):
            self._series[(location, metric)].append((d, avg, lo, hi, samples))

    def list_metrics(self) -> list[dict]:
        return [{"metric": m, "unit": spec[0]} for m, spec in sorted(METRICS.items())]

    def list_locations(self) -> list[str]:
        return sorted(LOCATIONS)

    def coverage(self) -> dict:
        rows = sum(len(v) for v in self._series.values())
        return {"first_day": HISTORY_START.isoformat(), "last_day": (self.last_day - timedelta(days=1)).isoformat(), "row_count": rows}

    def history(self, metric, location, start, end, granularity="auto") -> dict:
        g = pick_granularity(start, end, granularity)
        first, last = day_range(start, end)
        buckets: dict[date, list[tuple]] = defaultdict(list)
        for row in self._series.get((location, metric), []):
            if first <= row[0] < last:
                buckets[_bucket(row[0], g)].append(row)
        points = [
            make_point(k, sum(r[1] for r in rs) / len(rs), min(r[2] for r in rs), max(r[3] for r in rs), sum(r[4] for r in rs))
            for k, rs in sorted(buckets.items())
        ]
        return make_result(metric, location, metric_unit(metric), g, start, end, points, batches=[])

    def run_readonly_sql(self, sql: str, limit: int = 200) -> dict:
        check_readonly(sql)
        raise WarehouseUnavailable("Raw SQL needs a real Snowflake account. Set SNOWFLAKE_* in .env.local (see warehouse/README.md).")


_repo: WarehouseRepo | None = None


def get_repo() -> WarehouseRepo:
    global _repo
    if _repo is None:
        if is_configured():
            _repo = SnowflakeRepo()
        else:
            _repo = MockWarehouseRepo(int(os.getenv("RECENT_DAYS", "7")))
    return _repo
