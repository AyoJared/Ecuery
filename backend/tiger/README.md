# Tiger Data (step 3: recent data)

Recent environmental readings live in a Tiger Cloud service (TimescaleDB):

- `sensor_readings`: hypertable of raw 15-minute readings
- `readings_hourly` / `readings_daily`: continuous aggregates, refreshed automatically

Without `TIGER_DATABASE_URL`, everything runs on in-memory demo data (`mode: "mock"`).
The one exception is raw SQL, which needs a real service.

## 1. Tiger CLI: provisioning the database (you)

Install (PowerShell):

```powershell
irm https://cli.tigerdata.com/install.ps1 | iex
```

Create a service and get its connection string:

```powershell
tiger auth login
tiger service create --name ecuery
tiger db uri                      # copy this
```

Add it to `backend/.env.local`:

```
TIGER_DATABASE_URL=postgres://tsdbadmin:...@....tsdb.cloud.timescale.com:5432/tsdb?sslmode=require
```

Create the tables and load 14 days of demo readings (from `backend/`):

```powershell
python -m tiger.setup_db          # --days 30, or --schema-only
```

Useful day-to-day:

```powershell
tiger db psql                                                   # SQL shell
tiger db query -c "SELECT count(*) FROM sensor_readings"
tiger db schema                                                 # tables, views, indexes
```

## 2. Tiger MCP: your AI coding assistant

Tiger's own MCP server lets Claude Code, Cursor or Gemini CLI inspect the schema,
run queries and manage services while you build:

```powershell
tiger mcp install                 # pick your editor, or e.g. `tiger mcp install gemini`
```

It includes tools like `service_create` and `service_delete`, so it's a dev tool, not something to hand to the app's Gemini.

## 3. Ecuery MCP: the app's Gemini

`backend/mcp_server.py` (server name `ecuery-data`) exposes read-only tools over **both** Tiger and Snowflake:

| Tool | Purpose |
| --- | --- |
| `list_metrics` / `list_locations` | Valid names to use in queries |
| `data_coverage` | Where the recent/historical split is, date ranges |
| `get_readings(metric, location, start, end, days)` | Any time range, routed to Tiger and/or Snowflake and merged (main tool) |
| `get_recent_readings(metric, location, hours, granularity)` | Detailed recent data from Tiger |
| `compare_recent_to_history(metric, location, days, years)` | Is this week normal? |
| `describe_schema(database)` | Tables/columns for `tiger` or `snowflake` |
| `run_readonly_sql(sql, database, limit)` | Gemini-generated SELECT, checked by `shared/sql_guard.py`, then run read-only (READ ONLY transaction on Tiger, `ECUERY_READER` role on Snowflake) |

Run it from `backend/`:

```powershell
python mcp_server.py              # stdio
python mcp_server.py --http 8001  # http://127.0.0.1:8001/mcp
```

Gemini CLI (`~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "ecuery-data": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "C:/Users/Jared/Dev/Owlhacks/Fall2026/Ecuery/backend"
    }
  }
}
```

Gemini API (Python `google-genai`, not wired up yet) can take an MCP session directly as a tool:

```python
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command="python", args=["mcp_server.py"])
async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
    await session.initialize()
    response = await genai.Client().aio.models.generate_content(
        model="gemini-2.5-flash",
        contents="Was PM2.5 in Philadelphia this week higher than usual?",
        config=types.GenerateContentConfig(tools=[session]),
    )
```

## 4. HTTP API (for the frontend)

- `GET /tiger/status`: `mock` or `tiger`, plus the schema
- `GET /tiger/metrics`
- `GET /tiger/locations`
- `GET /tiger/recent?metric=pm25&location=philadelphia&hours=72`: `granularity` is `auto`/`raw`/`hourly`/`daily`
- `POST /tiger/sql`: `{"sql": "SELECT ...", "limit": 200}`
