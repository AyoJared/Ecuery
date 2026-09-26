"""Ecuery's MCP server over Tiger Data, for Gemini (or any MCP client).

Exposes a small, read-only set of tools instead of Tiger's own MCP server,
which also has service create/delete tools meant for coding assistants.

Run from backend/:
    python -m tiger.mcp_server                 # stdio (Gemini SDK / Gemini CLI spawn it)
    python -m tiger.mcp_server --http 8001     # streamable HTTP at http://127.0.0.1:8001/mcp
"""

import argparse
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from .repo import MAX_HOURS, SCHEMA_DESCRIPTION, TigerUnavailable, get_repo, resolve_window  # noqa: E402
from .sql_guard import UnsafeSQL  # noqa: E402

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

mcp = MCPServer(
    name="ecuery-tiger",
    instructions=(
        "Recent environmental readings (air quality, CO2, weather) stored in Tiger Data. "
        "Call list_metrics / list_locations first to get valid names. Prefer get_recent_readings; "
        "use run_readonly_sql only for questions it can't answer, after reading describe_schema. "
        f"Data covers roughly the last {MAX_HOURS // 24} days."
    ),
)


def _db(fn, *args):
    # ToolError messages reach the model; other exceptions become a generic error.
    try:
        return fn(*args)
    except TigerUnavailable as e:
        raise ToolError(str(e)) from None


@mcp.tool(annotations=READ_ONLY)
def list_metrics() -> list[dict]:
    """List the environmental metrics available (e.g. pm25, o3, co2) with their units."""
    return _db(get_repo().list_metrics)


@mcp.tool(annotations=READ_ONLY)
def list_locations() -> list[str]:
    """List the locations that have sensor data (lowercase snake_case city names)."""
    return _db(get_repo().list_locations)


@mcp.tool(annotations=READ_ONLY)
def get_recent_readings(
    metric: str,
    location: str,
    hours: float = 24,
    granularity: Literal["auto", "raw", "hourly", "daily"] = "auto",
) -> dict:
    """Get readings for one metric at one location over the last `hours` hours.

    granularity: "auto" (default), "raw" (15-minute), "hourly", or "daily".
    Returns a summary (avg/min/max/latest) plus the time-series points for charting.
    An empty result (count 0) means that metric/location has no data in the window.
    """
    try:
        start, end = resolve_window(hours)
    except ValueError as e:
        return {"error": f"Invalid time range: {e}. hours must be > 0."}
    return _db(get_repo().recent, metric.lower(), location.lower(), start, end, granularity)


@mcp.tool(annotations=READ_ONLY)
def describe_schema() -> str:
    """Describe the Tiger Data tables and columns, for writing SQL."""
    return SCHEMA_DESCRIPTION


@mcp.tool(annotations=READ_ONLY)
def run_readonly_sql(sql: str, limit: int = 200) -> dict:
    """Run one read-only Postgres SELECT against the readings tables (see describe_schema).

    Writes, multiple statements and comments are rejected; results are capped at `limit` rows.
    """
    try:
        return get_repo().run_readonly_sql(sql, max(1, min(limit, 1000)))
    except (UnsafeSQL, TigerUnavailable) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Query failed: {e}"}


def main():
    parser = argparse.ArgumentParser(description="Ecuery Tiger Data MCP server")
    parser.add_argument("--http", type=int, metavar="PORT", help="serve streamable HTTP on PORT instead of stdio")
    args = parser.parse_args()
    if args.http:
        mcp.run("streamable-http", port=args.http)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
