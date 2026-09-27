"""Write batches into Tiger (recent) / Snowflake (history), and keep the provenance registry in Tiger."""

import json
import os
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from .provenance import Batch, rows_sha256

TIGER_SCHEMA = [
    "ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS batch_id TEXT",
    "CREATE INDEX IF NOT EXISTS sensor_readings_batch ON sensor_readings (batch_id)",
    """CREATE TABLE IF NOT EXISTS ingest_batches (
        batch_id         TEXT PRIMARY KEY,
        source           TEXT NOT NULL,
        dataset          TEXT NOT NULL,
        quality          TEXT NOT NULL,
        store            TEXT NOT NULL,
        fetched_at       TIMESTAMPTZ NOT NULL,
        row_count        INTEGER NOT NULL,
        rows_sha256      TEXT NOT NULL,
        manifest         JSONB NOT NULL,
        manifest_sha256  TEXT NOT NULL,
        solana_signature TEXT,
        solana_cluster   TEXT,
        chain_mode       TEXT,
        anchor_error     TEXT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now())""",
]
SNOWFLAKE_SCHEMA = ["ALTER TABLE DAILY_READINGS ADD COLUMN IF NOT EXISTS BATCH_ID VARCHAR"]


def tiger_conn(**kw):
    return psycopg.connect(os.environ["TIGER_DATABASE_URL"], connect_timeout=15, **kw)


def snowflake_conn():
    import snowflake.connector

    from warehouse.config import connect_params
    return snowflake.connector.connect(**connect_params())


def ensure_schema() -> None:
    with tiger_conn(autocommit=True) as conn:
        for sql in TIGER_SCHEMA:
            conn.execute(sql)
    with snowflake_conn() as conn, conn.cursor() as cur:
        for sql in SNOWFLAKE_SCHEMA:
            cur.execute(sql)


def _dedupe(batch: Batch) -> None:
    # One value per (time/day, location, metric); the last one wins.
    batch.rows = list({r[:3]: r for r in batch.rows}.values())


def load_tiger(batch: Batch) -> int:
    _dedupe(batch)
    with tiger_conn() as conn, conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE staging (time TIMESTAMPTZ, location TEXT, metric TEXT, value DOUBLE PRECISION, "
                    "unit TEXT) ON COMMIT DROP")
        with cur.copy("COPY staging (time, location, metric, value, unit) FROM STDIN") as copy:
            for row in batch.rows:
                copy.write_row(row)
        cur.execute("""INSERT INTO sensor_readings (time, location, metric, value, unit, source, batch_id)
                       SELECT time, location, metric, value, unit, %s, %s FROM staging
                       ON CONFLICT (location, metric, source, time)
                       DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit, batch_id = EXCLUDED.batch_id""",
                    (batch.source, batch.batch_id))
        return cur.rowcount


def load_snowflake(batch: Batch) -> int:
    _dedupe(batch)
    with snowflake_conn() as conn, conn.cursor() as cur:
        cur.execute("CREATE OR REPLACE TEMPORARY TABLE STG (DAY DATE, LOCATION VARCHAR, METRIC VARCHAR, UNIT VARCHAR, "
                    "AVG_VALUE FLOAT, MIN_VALUE FLOAT, MAX_VALUE FLOAT, SAMPLES INTEGER)")
        for i in range(0, len(batch.rows), 5000):
            cur.executemany("INSERT INTO STG VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", batch.rows[i:i + 5000])
        cur.execute("""MERGE INTO DAILY_READINGS t
                       USING (SELECT *, %s AS SOURCE, %s AS BATCH_ID FROM STG) s
                       ON t.DAY = s.DAY AND t.LOCATION = s.LOCATION AND t.METRIC = s.METRIC AND t.SOURCE = s.SOURCE
                       WHEN MATCHED THEN UPDATE SET UNIT = s.UNIT, AVG_VALUE = s.AVG_VALUE, MIN_VALUE = s.MIN_VALUE,
                            MAX_VALUE = s.MAX_VALUE, SAMPLES = s.SAMPLES, BATCH_ID = s.BATCH_ID
                       WHEN NOT MATCHED THEN INSERT (DAY, LOCATION, METRIC, UNIT, AVG_VALUE, MIN_VALUE, MAX_VALUE, SAMPLES, SOURCE, BATCH_ID)
                            VALUES (s.DAY, s.LOCATION, s.METRIC, s.UNIT, s.AVG_VALUE, s.MIN_VALUE, s.MAX_VALUE, s.SAMPLES, s.SOURCE, s.BATCH_ID)""",
                    (batch.source, batch.batch_id))
        return len(batch.rows)


def register(batch: Batch, manifest: dict, anchored: dict) -> None:
    with tiger_conn() as conn:
        conn.execute("""INSERT INTO ingest_batches (batch_id, source, dataset, quality, store, fetched_at, row_count,
                            rows_sha256, manifest, manifest_sha256, solana_signature, solana_cluster, chain_mode, anchor_error)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                     (batch.batch_id, batch.source, batch.dataset, batch.quality, batch.store,
                      datetime.fromisoformat(batch.fetched_at), manifest["row_count"], manifest["rows_sha256"],
                      json.dumps(manifest), anchored["manifest_sha256"], anchored.get("signature"),
                      anchored.get("cluster"), anchored.get("chain_mode"), anchored.get("error")))


def registry(batch_ids: list[str] | None = None, limit: int = 50) -> list[dict]:
    with tiger_conn(row_factory=dict_row) as conn:
        if batch_ids is not None:
            return conn.execute("SELECT * FROM ingest_batches WHERE batch_id = ANY(%s)", (batch_ids,)).fetchall()
        return conn.execute("SELECT * FROM ingest_batches ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()


def stored_rows(batch_id: str, store: str) -> list[tuple]:
    """The rows currently in the database for a batch, in the same shape they were hashed at ingest."""
    if store == "tiger":
        with tiger_conn() as conn:
            return [tuple(r) for r in conn.execute(
                "SELECT time, location, metric, value, unit FROM sensor_readings WHERE batch_id = %s", (batch_id,))]
    with snowflake_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT DAY, LOCATION, METRIC, UNIT, AVG_VALUE, MIN_VALUE, MAX_VALUE, SAMPLES "
                    "FROM DAILY_READINGS WHERE BATCH_ID = %s", (batch_id,))
        return [tuple(r) for r in cur.fetchall()]


def delete_demo_data() -> dict:
    with tiger_conn() as conn:
        tiger = conn.execute("DELETE FROM sensor_readings WHERE source = 'demo-sensor'").rowcount
    with snowflake_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM DAILY_READINGS WHERE SOURCE = 'demo-history'")
        snowflake = cur.rowcount
    return {"tiger": tiger, "snowflake": snowflake}


def refresh_aggregates() -> None:
    with tiger_conn(autocommit=True) as conn:
        for view in ("readings_hourly", "readings_daily"):
            conn.execute(f"CALL refresh_continuous_aggregate('{view}', NULL, NULL)")


def rows_hash_now(batch_id: str, store: str) -> tuple[int, str]:
    rows = stored_rows(batch_id, store)
    return len(rows), rows_sha256(rows)


def unanchored() -> list[dict]:
    with tiger_conn(row_factory=dict_row) as conn:
        return conn.execute("SELECT batch_id, manifest FROM ingest_batches WHERE solana_signature IS NULL").fetchall()


def set_anchor(batch_id: str, anchored: dict) -> None:
    with tiger_conn() as conn:
        conn.execute("""UPDATE ingest_batches SET solana_signature = %s, solana_cluster = %s, chain_mode = %s,
                        anchor_error = %s WHERE batch_id = %s""",
                     (anchored.get("signature"), anchored.get("cluster"), anchored.get("chain_mode"),
                      anchored.get("error"), batch_id))
