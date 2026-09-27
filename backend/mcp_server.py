"""Ecuery's MCP server: read-only environmental data tools for Gemini.

Covers both stores from the diagram: Tiger Data (recent) and Snowflake
(historical), plus the routed/merged view across them.

Run from backend/:
    python mcp_server.py               # stdio (Gemini SDK / Gemini CLI spawn it)
    python mcp_server.py --http 8001   # streamable HTTP at http://127.0.0.1:8001/mcp
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

load_dotenv(Path(__file__).resolve().parent / ".env.local")

from readings import service as merged  # noqa: E402
from readings.service import RECENT_DAYS, recent_cutoff  # noqa: E402
from ingest.on_demand import ensure  # noqa: E402
from shared import places  # noqa: E402
from shared.catalog import GLOBAL, METRICS  # noqa: E402
from shared.series import DataUnavailable, error_text, parse_time  # noqa: E402
from shared.sql_guard import UnsafeSQL  # noqa: E402
from tiger.repo import SCHEMA_DESCRIPTION as TIGER_SCHEMA, get_repo as get_tiger, resolve_window  # noqa: E402
from warehouse.repo import SCHEMA_DESCRIPTION as SNOWFLAKE_SCHEMA, get_repo as get_warehouse  # noqa: E402

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

mcp = MCPServer(
    name="ecuery-data",
    instructions=(
        "Environmental data (air quality, weather, river flow, global CO2) for any place on Earth. "
        "Pass locations as place names ('Delhi', 'Paris, France', 'Philadelphia'); a new place is fetched on first use "
        "(a few seconds). A few US cities use measured EPA/NOAA/USGS data; elsewhere values are modeled "
        "(Copernicus CAMS, ECMWF ERA5, GloFAS). "
        f"The last {RECENT_DAYS} days live in Tiger Data; older daily history lives in Snowflake. "
        "get_readings handles any time range and merges both stores. Use compare_recent_to_history for 'is this "
        "normal / higher than usual' "
        "questions. Only write SQL (run_readonly_sql) when the other tools can't answer, after describe_schema."
    ),
)


def _place(location: str, metric: str) -> str:
    """Any place name ("Delhi", "Paris, France", "new_york") -> location key, loading its data if it's new."""
    if METRICS.get(metric.lower()) and METRICS[metric.lower()].global_only:
        return GLOBAL
    try:
        place = places.resolve(location)
    except places.PlaceNotFound as e:
        raise ToolError(f"{e}. Try adding the country, e.g. 'Paris, France'.") from None
    ensure(place, [metric.lower()])
    return place.key


def _call(fn, *args):
    # ToolError messages reach the model; other exceptions become a generic error.
    try:
        return fn(*args)
    except DataUnavailable as e:
        raise ToolError(str(e)) from None


@mcp.tool(annotations=READ_ONLY)
def list_metrics() -> list[dict]:
    """List the environmental metrics available (e.g. pm25, o3, co2) with their units."""
    return _call(get_tiger().list_metrics)


@mcp.tool(annotations=READ_ONLY)
def list_locations() -> list[str]:
    """Location keys that already have data stored. Any other place name also works in the other tools."""
    return _call(get_tiger().list_locations)


@mcp.tool(annotations=READ_ONLY)
def data_coverage() -> dict:
    """Where recent vs historical data lives and what date range each store covers."""
    return {
        "recent": {"store": "tiger", "mode": get_tiger().mode, "from": recent_cutoff().isoformat()},
        "historical": {"store": "snowflake", "mode": get_warehouse().mode, **_call(get_warehouse().coverage)},
    }


@mcp.tool(annotations=READ_ONLY)
def get_readings(metric: str, location: str, start: str | None = None, end: str | None = None,
                 days: float = 30) -> dict:
    """Readings for one metric at one location over any time range, routed to Tiger and/or Snowflake and merged.

    Give ISO dates `start`/`end` (e.g. "2023-06-01", "2023-06-15"), or `days` back from now.
    Each point has a `source` ("tiger" or "snowflake"); the result has `route`, `summary` and chart `points`.
    """
    try:
        end_dt = parse_time(end) if end else datetime.now(timezone.utc)
        start_dt = parse_time(start) if start else end_dt - timedelta(days=days)
    except ValueError as e:
        return {"error": f"Invalid date: {e}. Use ISO format like 2023-06-01."}
    if start_dt >= end_dt:
        return {"error": "start must be before end"}
    return _call(merged.get_readings, metric, _place(location, metric), start_dt, end_dt)


@mcp.tool(annotations=READ_ONLY)
def get_recent_readings(metric: str, location: str, hours: float = 24,
                        granularity: Literal["auto", "raw", "hourly", "daily"] = "auto") -> dict:
    """Detailed recent readings from Tiger (15-minute / hourly / daily) over the last `hours` hours."""
    try:
        start, end = resolve_window(hours)
    except ValueError as e:
        return {"error": f"Invalid time range: {e}. hours must be > 0."}
    return _call(get_tiger().recent, metric.lower(), _place(location, metric), start, end, granularity)


@mcp.tool(annotations=READ_ONLY)
def compare_recent_to_history(metric: str, location: str, days: int = 7, years: int = 5) -> dict:
    """Compare the last `days` days with the same calendar window in each of the previous `years` years.

    Returns the recent average, the historical baseline, percent change and a per-year breakdown.
    """
    days = max(1, min(days, RECENT_DAYS))
    years = max(1, min(years, 20))
    return _call(merged.compare_to_history, metric, _place(location, metric), days, years)


@mcp.tool(annotations=READ_ONLY)
def describe_schema(database: Literal["tiger", "snowflake"]) -> str:
    """Describe the tables and SQL dialect of one store, for writing run_readonly_sql queries."""
    return TIGER_SCHEMA if database == "tiger" else SNOWFLAKE_SCHEMA


@mcp.tool(annotations=READ_ONLY)
def run_readonly_sql(sql: str, database: Literal["tiger", "snowflake"], limit: int = 200) -> dict:
    """Run one read-only SELECT against Tiger (Postgres dialect) or Snowflake (Snowflake dialect).

    Writes, multiple statements and comments are rejected; results are capped at `limit` rows.
    """
    repo = get_tiger() if database == "tiger" else get_warehouse()
    try:
        return repo.run_readonly_sql(sql, max(1, min(limit, 1000)))
    except (UnsafeSQL, DataUnavailable) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Query failed: {error_text(e)}"}


def main():
    parser = argparse.ArgumentParser(description="Ecuery data MCP server")
    parser.add_argument("--http", type=int, metavar="PORT", help="serve streamable HTTP on PORT instead of stdio")
    args = parser.parse_args()
    if args.http:
        mcp.run("streamable-http", port=args.http)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
