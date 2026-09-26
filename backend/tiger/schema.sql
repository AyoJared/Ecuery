-- Step 3: Tiger Data (TimescaleDB) schema for recent environmental readings.
-- Applied by `python -m tiger.setup_db`. Each statement runs on its own
-- (continuous aggregates can't be created inside a transaction).

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 3a: raw sensor readings, one row per (time, location, metric, source)
CREATE TABLE IF NOT EXISTS sensor_readings (
    time      TIMESTAMPTZ      NOT NULL,
    location  TEXT             NOT NULL,
    metric    TEXT             NOT NULL,
    value     DOUBLE PRECISION NOT NULL,
    unit      TEXT             NOT NULL,
    source    TEXT             NOT NULL
);

SELECT create_hypertable('sensor_readings', by_range('time', INTERVAL '1 day'), if_not_exists => TRUE);

CREATE UNIQUE INDEX IF NOT EXISTS sensor_readings_uniq
    ON sensor_readings (location, metric, source, time);

-- 3b: continuous aggregates. materialized_only = false means queries also
-- include rows newer than the last refresh (real-time aggregation).
CREATE MATERIALIZED VIEW IF NOT EXISTS readings_hourly
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 hour', time) AS bucket,
       location, metric, unit,
       avg(value) AS avg_value,
       min(value) AS min_value,
       max(value) AS max_value,
       count(*)   AS samples
FROM sensor_readings
GROUP BY bucket, location, metric, unit
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS readings_daily
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 day', time) AS bucket,
       location, metric, unit,
       avg(value) AS avg_value,
       min(value) AS min_value,
       max(value) AS max_value,
       count(*)   AS samples
FROM sensor_readings
GROUP BY bucket, location, metric, unit
WITH NO DATA;

SELECT add_continuous_aggregate_policy('readings_hourly',
    start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes', if_not_exists => TRUE);

SELECT add_continuous_aggregate_policy('readings_daily',
    start_offset => INTERVAL '35 days', end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE);
