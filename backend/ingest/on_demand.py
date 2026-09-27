"""Fetch-on-demand for places without local monitors (the "whole world" part).

The first question about a place loads its history into Snowflake and its last RECENT_DAYS
into Tiger, one provider at a time, each as a provenance batch anchored on Solana. Coverage
is remembered in Tiger (`place_coverage`), so later questions only top up what's missing:
history once a day, recent data at most hourly.
"""

import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from readings.service import RECENT_DAYS, recent_cutoff
from shared.places import Place

from . import global_sources as g
from .commit import commit
from .store import tiger_conn

PROVIDERS = {  # provider -> metrics it supplies
    "air": ("pm25", "o3", "no2"),
    "weather": ("temperature", "humidity"),
    "river": ("streamflow",),
}
METRIC_PROVIDER = {m: p for p, ms in PROVIDERS.items() for m in ms}
HISTORY_START = {"air": g.AIR_HISTORY_START, "weather": date(2019, 1, 1), "river": date(2019, 1, 1)}
RECENT_REFRESH = timedelta(hours=1)

SCHEMA = """CREATE TABLE IF NOT EXISTS place_coverage (
    location TEXT NOT NULL, provider TEXT NOT NULL, history_until DATE, recent_at TIMESTAMPTZ,
    PRIMARY KEY (location, provider))"""

_locks: dict[tuple, threading.Lock] = defaultdict(threading.Lock)
_ready = False


def _coverage(conn, location: str, provider: str):
    return conn.execute("SELECT history_until, recent_at FROM place_coverage WHERE location = %s AND provider = %s",
                        (location, provider)).fetchone()


def _save(location: str, provider: str, history_until: date | None, recent_at: datetime | None) -> None:
    with tiger_conn() as conn:
        conn.execute("""INSERT INTO place_coverage (location, provider, history_until, recent_at) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (location, provider) DO UPDATE SET
                          history_until = COALESCE(EXCLUDED.history_until, place_coverage.history_until),
                          recent_at = COALESCE(EXCLUDED.recent_at, place_coverage.recent_at)""",
                     (location, provider, history_until, recent_at))


def ensure(place: Place, metrics: list[str]) -> dict:
    """Make sure Tiger/Snowflake hold data for these metrics at this place. Returns what was loaded."""
    global _ready
    if place.kind != "modeled":
        return {}
    if not _ready:
        with tiger_conn() as conn:
            conn.execute(SCHEMA)
        _ready = True

    providers = list(dict.fromkeys(METRIC_PROVIDER[m] for m in metrics if m in METRIC_PROVIDER))

    def one(provider: str):
        with _locks[(place.key, provider)]:  # two questions about a new place mustn't both load it
            return provider, _ensure_provider(place, provider)

    with ThreadPoolExecutor(max(1, len(providers))) as pool:
        loaded = dict(pool.map(one, providers))
    if any("recent" in v for v in loaded.values()):
        _refresh_aggregates(recent_cutoff())
    return loaded


def _refresh_aggregates(since: datetime) -> None:
    """New rows older than the aggregates' watermark stay invisible until the window is refreshed."""
    with tiger_conn(autocommit=True) as conn:
        for view in ("readings_hourly", "readings_daily"):
            conn.execute(f"CALL refresh_continuous_aggregate('{view}', %s, NULL)", (since - timedelta(days=1),))


def _ensure_provider(place: Place, provider: str) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = recent_cutoff()
    with tiger_conn() as conn:
        row = _coverage(conn, place.key, provider)
    history_until, recent_at = (row or (None, None))
    tasks = {}

    if history_until is None or history_until < cutoff.date():
        start = history_until or HISTORY_START[provider]
        batch = {"air": lambda: g.cams_history(place, start, cutoff.date()),
                 "weather": lambda: g.era5_history(place, start, cutoff.date()),
                 "river": lambda: g.glofas(place, start, cutoff.date(), "snowflake")}[provider]
        tasks["history"] = (batch, lambda: _save(place.key, provider, cutoff.date(), None))

    if recent_at is None or now - recent_at > RECENT_REFRESH:
        batch = {"air": lambda: g.cams_recent(place, cutoff, now),
                 "weather": lambda: g.weather_recent(place, cutoff, now, RECENT_DAYS),
                 "river": lambda: g.glofas(place, cutoff.date(), now.date() + timedelta(days=1), "tiger")}[provider]
        tasks["recent"] = (batch, lambda: _save(place.key, provider, None, now))

    def run(item):
        name, (batch_fn, save) = item
        batch = batch_fn()
        anchored = commit(batch)
        save()
        return name, {"batch_id": batch.batch_id, "rows": len(batch.rows),
                      "anchored": bool(anchored and anchored.get("signature"))}

    with ThreadPoolExecutor(2) as pool:  # history (Snowflake) and recent (Tiger) load side by side
        return dict(pool.map(run, tasks.items()))
