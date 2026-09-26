# Snowflake (step 4: historical data)

Years of daily readings live in Snowflake (`ECUERY.HISTORY.DAILY_READINGS`,
plus a `MONTHLY_READINGS` view). Tiger holds the last `RECENT_DAYS` (default 14);
Snowflake holds everything before that. `/readings` routes and merges across both.

Without `SNOWFLAKE_*` settings, a mock with the same demo history is used (`mode: "mock"`).

## Setup

1. Create a Snowflake account (the free trial works). Note your **account identifier**:
   in Snowsight, open your profile menu → *Connect a tool to Snowflake*. It looks like `orgname-accountname`.
2. Add to `backend/.env.local`:
   ```
   SNOWFLAKE_ACCOUNT="orgname-accountname"
   SNOWFLAKE_USER="your_user"
   SNOWFLAKE_PASSWORD="your_password_or_programmatic_access_token"
   SNOWFLAKE_ROLE="ACCOUNTADMIN"     # needs rights to create a warehouse, database and role
   ```
   **If the account requires MFA** (error 390197), use key-pair auth instead:
   - Generate a key pair. `backend/snowflake_key.p8` is private and git-ignored; `snowflake_key.pub` is the public half.
   - In a Snowsight worksheet, run `ALTER USER <you> SET RSA_PUBLIC_KEY='<contents of snowflake_key.pub>';`
   - Add `SNOWFLAKE_PRIVATE_KEY_FILE="snowflake_key.p8"` to `.env.local`. It takes priority over the password.
3. Create everything and load demo history (from `backend/`):
   ```powershell
   python -m warehouse.setup_db
   ```
   This creates:
   - an XSMALL warehouse `ECUERY_WH` that auto-suspends after 60s
   - the database, table and view
   - a read-only role `ECUERY_READER`

   It then loads about 67k daily rows from 2019 up to the Tiger window.
4. Restart the API. `/warehouse/status` should say `"mode": "snowflake"`.

Gemini's SQL runs as `ECUERY_READER`, which only has SELECT, so Snowflake itself blocks writes.

Snowflake users default to `DEFAULT_SECONDARY_ROLES = ('ALL')`. That quietly adds every role you have,
including ACCOUNTADMIN, to a session. The reader connection runs `USE SECONDARY ROLES NONE`, checks that
it took effect, and refuses to run SQL otherwise (`SnowflakeRepo._lock_down`).

## Demo data worth asking about

- June 7, 2023: Canadian wildfire smoke. PM2.5 daily averages spike, worst in New York.
- April–May 2020: lockdown NO2 drop.
- CO2 climbs about 2.4 ppm per year, and PM2.5 declines slowly.

Rows are tagged `SOURCE = 'demo-history'`. Remove them once real data is loaded:
`DELETE FROM DAILY_READINGS WHERE SOURCE = 'demo-history'`.

## HTTP API

- `GET /warehouse/status`: mode + date coverage
- `GET /warehouse/history?metric=pm25&location=new_york&start=2023-06-01&end=2023-06-15`: `granularity` is `auto`/`daily`/`monthly`/`yearly`, or use `years=5` instead of dates
- `POST /warehouse/sql`: `{"sql": "SELECT ...", "limit": 200}` (Snowflake dialect)

Merged across Tiger + Snowflake:

- `GET /readings?metric=pm25&location=philadelphia&days=365`: or `start`/`end`; every point has a `source`
- `GET /readings/compare?metric=pm25&location=philadelphia&days=7&years=5`: recent vs same week in past years
- `GET /readings/sources`: which stores are live and where the split is
