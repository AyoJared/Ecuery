"""Natural disasters and other environmental events (tornadoes, earthquakes, wildfires, ...).

Unlike readings (a number over time at a place), events are records with a time, a location
and details. They live in the Tiger table `events` and are loaded one source-year at a time,
the first time a question needs that year, as provenance batches anchored on Solana:

  noaa-storm-events  NOAA NCEI Storm Events Database: every NWS-verified US storm event
                     (tornado EF rating/path, hail, wind, floods, hurricanes, winter storms, heat)
  usgs-earthquakes   USGS ComCat, worldwide, magnitude 2.5+
  nasa-eonet         NASA EONET, worldwide wildfires, severe storms, volcanoes, floods, landslides

Questions search a radius around a place (shared/places.py), so they work anywhere.
"""

import csv
import gzip
import io
import json
import math
import re
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from psycopg.rows import dict_row

from .commit import commit
from .provenance import Batch, _http
from .store import tiger_conn

EVENT_TYPES = {
    "tornado": "Tornado", "hail": "Hail", "thunderstorm_wind": "Damaging thunderstorm wind", "flood": "Flood",
    "hurricane": "Hurricane / tropical storm", "winter_storm": "Winter storm", "heat": "Extreme heat",
    "wildfire": "Wildfire", "drought": "Drought", "earthquake": "Earthquake", "volcano": "Volcanic eruption",
    "landslide": "Landslide", "severe_storm": "Severe storm",
}
# Which sources can answer which types (US-only types come from NOAA Storm Events).
TYPE_SOURCES = {
    "tornado": ["noaa-storm-events"], "hail": ["noaa-storm-events"], "thunderstorm_wind": ["noaa-storm-events"],
    "flood": ["noaa-storm-events", "nasa-eonet"], "hurricane": ["noaa-storm-events", "nasa-eonet"],
    "winter_storm": ["noaa-storm-events"], "heat": ["noaa-storm-events"], "drought": ["noaa-storm-events", "nasa-eonet"],
    "wildfire": ["noaa-storm-events", "nasa-eonet"], "earthquake": ["usgs-earthquakes"],
    "volcano": ["nasa-eonet"], "landslide": ["noaa-storm-events", "nasa-eonet"], "severe_storm": ["nasa-eonet"],
}
DEFAULT_RADIUS_KM = {"earthquake": 250, "volcano": 300, "hurricane": 200, "wildfire": 150, "drought": 150}
CITY_RADIUS_KM = 25


def default_radius(types: list[str], place_radius_km: float | None) -> float:
    """Search radius: the place's own extent, widened for events felt far away (earthquakes, hurricanes)."""
    return max([place_radius_km or CITY_RADIUS_KM] + [DEFAULT_RADIUS_KM.get(t, 0) for t in types])


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS events (
        source TEXT NOT NULL, event_id TEXT NOT NULL, type TEXT NOT NULL, name TEXT,
        starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ,
        lat DOUBLE PRECISION, lon DOUBLE PRECISION, end_lat DOUBLE PRECISION, end_lon DOUBLE PRECISION,
        magnitude DOUBLE PRECISION, magnitude_label TEXT, deaths INTEGER, injuries INTEGER, damage_usd DOUBLE PRECISION,
        region TEXT, details JSONB, batch_id TEXT, PRIMARY KEY (source, event_id))""",
    "CREATE INDEX IF NOT EXISTS events_type_time ON events (type, starts_at)",
    "CREATE INDEX IF NOT EXISTS events_batch ON events (batch_id)",
    """CREATE TABLE IF NOT EXISTS event_coverage (
        source TEXT NOT NULL, year INTEGER NOT NULL, loaded_at TIMESTAMPTZ NOT NULL, version TEXT,
        PRIMARY KEY (source, year))""",
]
_ready = False
_locks: dict[tuple, threading.Lock] = defaultdict(threading.Lock)


def ensure_schema() -> None:
    global _ready
    if not _ready:
        with tiger_conn(autocommit=True) as conn:
            for sql in SCHEMA:
                conn.execute(sql)
        _ready = True


# ---------------------------------------------------------------- NOAA Storm Events (US)

STORM_BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
NCEI_TYPES = {
    "Tornado": "tornado", "Waterspout": None, "Hail": "hail", "Marine Hail": None, "Thunderstorm Wind": "thunderstorm_wind",
    "Flood": "flood", "Flash Flood": "flood", "Coastal Flood": "flood", "Lakeshore Flood": "flood",
    "Hurricane (Typhoon)": "hurricane", "Hurricane": "hurricane", "Tropical Storm": "hurricane", "Tropical Depression": "hurricane",
    "Storm Surge/Tide": "hurricane", "Winter Storm": "winter_storm", "Blizzard": "winter_storm", "Ice Storm": "winter_storm",
    "Heavy Snow": "winter_storm", "Heat": "heat", "Excessive Heat": "heat", "Wildfire": "wildfire", "Drought": "drought",
    "Debris Flow": "landslide",
}


def _damage(text: str) -> float | None:
    m = re.fullmatch(r"([\d.]+)([KMB]?)", (text or "").strip().upper())
    if not m:
        return None
    return float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)]


def _ncei_time(text: str) -> datetime:
    # "16-MAY-25 11:42:00" in the event's local time zone; kept as-is but tagged UTC-agnostic (date is what matters)
    return datetime.strptime(text, "%d-%b-%y %H:%M:%S").replace(tzinfo=timezone.utc)


def storm_events_file(year: int) -> tuple[str, str] | None:
    index = _http.get(STORM_BASE).text
    stamps = re.findall(rf"StormEvents_details-ftp_v1\.0_d{year}_c(\d{{8}})\.csv\.gz", index)
    return (f"{STORM_BASE}StormEvents_details-ftp_v1.0_d{year}_c{max(stamps)}.csv.gz", max(stamps)) if stamps else None


def noaa_storm_events(year: int) -> tuple[Batch, str | None]:
    found = storm_events_file(year)
    batch = Batch("noaa-storm-events", f"NOAA NCEI Storm Events Database {year}", "official", "events")
    if not found:
        return batch, None
    url, version = found
    batch.dataset += f" (file version {version})"
    body = gzip.decompress(batch.fetch(url)).decode("latin-1")
    for r in csv.DictReader(io.StringIO(body)):
        kind = NCEI_TYPES.get(r["EVENT_TYPE"])
        if not kind:
            continue
        lat = float(r["BEGIN_LAT"]) if r["BEGIN_LAT"] else None
        lon = float(r["BEGIN_LON"]) if r["BEGIN_LON"] else None
        mag, label = None, None
        if kind == "tornado" and r["TOR_F_SCALE"]:
            label = r["TOR_F_SCALE"]
            digits = re.sub(r"\D", "", label)
            mag = float(digits) if digits else None
        elif r["MAGNITUDE"]:
            mag = float(r["MAGNITUDE"])
            label = f"{r['MAGNITUDE']} {'in' if kind == 'hail' else r['MAGNITUDE_TYPE'] or 'kt'}".strip()
        where = f"{r['BEGIN_LOCATION'].title()}, " if r["BEGIN_LOCATION"] else ""
        details = {k: r[k] for k in ("EVENT_TYPE", "TOR_LENGTH", "TOR_WIDTH", "EVENT_NARRATIVE", "EPISODE_ID", "WFO") if r.get(k)}
        batch.rows.append((
            "noaa-storm-events", r["EVENT_ID"], kind, r["EVENT_TYPE"], _ncei_time(r["BEGIN_DATE_TIME"]),
            _ncei_time(r["END_DATE_TIME"]), lat, lon,
            float(r["END_LAT"]) if r["END_LAT"] else None, float(r["END_LON"]) if r["END_LON"] else None,
            mag, label, int(r["DEATHS_DIRECT"] or 0) + int(r["DEATHS_INDIRECT"] or 0),
            int(r["INJURIES_DIRECT"] or 0) + int(r["INJURIES_INDIRECT"] or 0),
            (_damage(r["DAMAGE_PROPERTY"]) or 0) + (_damage(r["DAMAGE_CROPS"]) or 0) or None,
            f"{where}{r['CZ_NAME'].title()} County, {r['STATE'].title()}", _json(details)))
    return batch, version


# ---------------------------------------------------------------- USGS earthquakes (worldwide)

def usgs_earthquakes(year: int) -> tuple[Batch, str]:
    batch = Batch("usgs-earthquakes", f"USGS ComCat earthquakes M2.5+ worldwide {year}", "official", "events")
    today = datetime.now(timezone.utc).date()
    for q in range(4):  # quarters keep each request under the API's 20,000-event cap
        start = date(year, 3 * q + 1, 1)
        end = date(year + 1, 1, 1) if q == 3 else date(year, 3 * q + 4, 1)
        if start > today:
            break
        body = batch.fetch("https://earthquake.usgs.gov/fdsnws/event/1/query", {
            "format": "geojson", "starttime": start.isoformat(), "endtime": min(end, today + timedelta(days=1)).isoformat(),
            "minmagnitude": 2.5, "eventtype": "earthquake", "orderby": "time-asc"})
        for f in json.loads(body)["features"]:
            p, (lon, lat, depth) = f["properties"], f["geometry"]["coordinates"][:3]
            t = datetime.fromtimestamp(p["time"] / 1000, timezone.utc)
            batch.rows.append(("usgs-earthquakes", f["id"], "earthquake", p.get("title"), t, None, _f(lat), _f(lon), None, None,
                               _f(p.get("mag")), f"M{p['mag']}" if p.get("mag") is not None else None, None, None, None,
                               p.get("place"), _json({"depth_km": _f(depth), "tsunami": p.get("tsunami"),
                                                      "alert": p.get("alert"), "url": p.get("url")})))
    return batch, today.isoformat()


# ---------------------------------------------------------------- NASA EONET (worldwide)

EONET_TYPES = {"wildfires": "wildfire", "severeStorms": "severe_storm", "volcanoes": "volcano", "floods": "flood",
               "landslides": "landslide", "drought": "drought"}


def nasa_eonet(year: int) -> tuple[Batch, str]:
    batch = Batch("nasa-eonet", f"NASA EONET natural events {year}", "official", "events")
    today = datetime.now(timezone.utc).date()
    body = batch.fetch("https://eonet.gsfc.nasa.gov/api/v3/events", {
        "status": "all", "start": f"{year}-01-01", "end": min(date(year, 12, 31), today).isoformat()})
    for e in json.loads(body)["events"]:
        kind = next((EONET_TYPES[c["id"]] for c in e["categories"] if c["id"] in EONET_TYPES), None)
        points = [g for g in e["geometry"] if g["type"] == "Point"]
        if not kind or not points:
            continue
        first, last = points[0], points[-1]
        lon, lat = first["coordinates"]
        biggest = max((g for g in points if g.get("magnitudeValue") is not None), key=lambda g: g["magnitudeValue"], default=None)
        # Storm names like "Hurricane Erin" are hurricanes when they reached hurricane strength
        if kind == "severe_storm" and re.search(r"hurricane|typhoon|cyclone|tropical storm", e["title"], re.I):
            kind = "hurricane"
        batch.rows.append((
            "nasa-eonet", e["id"], kind, e["title"],
            datetime.fromisoformat(first["date"].replace("Z", "+00:00")),
            datetime.fromisoformat((e.get("closed") or last["date"]).replace("Z", "+00:00")),
            _f(lat), _f(lon), _f(last["coordinates"][1]), _f(last["coordinates"][0]),
            _f(biggest["magnitudeValue"]) if biggest else None,
            f"{biggest['magnitudeValue']:g} {biggest.get('magnitudeUnit') or ''}".strip() if biggest else None,
            None, None, None, None,
            _json({"sources": [s["url"] for s in e.get("sources", [])][:3], "points": len(points)})))
    return batch, today.isoformat()


# ---------------------------------------------------------------- loading + coverage

LOADERS = {"noaa-storm-events": noaa_storm_events, "usgs-earthquakes": usgs_earthquakes, "nasa-eonet": nasa_eonet}
FIRST_YEAR = {"noaa-storm-events": 1996, "usgs-earthquakes": 1990, "nasa-eonet": 2017}


def load_events(batch: Batch) -> None:
    batch.rows = list({(r[0], r[1]): r for r in batch.rows}.values())
    with tiger_conn() as conn, conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE staging (LIKE events INCLUDING DEFAULTS) ON COMMIT DROP")
        with cur.copy("COPY staging (source, event_id, type, name, starts_at, ends_at, lat, lon, end_lat, end_lon, "
                      "magnitude, magnitude_label, deaths, injuries, damage_usd, region, details) FROM STDIN") as copy:
            for row in batch.rows:
                copy.write_row(row)
        cur.execute("UPDATE staging SET batch_id = %s", (batch.batch_id,))
        cur.execute("""INSERT INTO events SELECT * FROM staging ON CONFLICT (source, event_id) DO UPDATE SET
                         type = EXCLUDED.type, name = EXCLUDED.name, starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at,
                         lat = EXCLUDED.lat, lon = EXCLUDED.lon, end_lat = EXCLUDED.end_lat, end_lon = EXCLUDED.end_lon,
                         magnitude = EXCLUDED.magnitude, magnitude_label = EXCLUDED.magnitude_label, deaths = EXCLUDED.deaths,
                         injuries = EXCLUDED.injuries, damage_usd = EXCLUDED.damage_usd, region = EXCLUDED.region,
                         details = EXCLUDED.details, batch_id = EXCLUDED.batch_id""")


def ensure_events(types: list[str], start: datetime, end: datetime) -> dict:
    """Load every source-year the question needs that isn't loaded (or is stale) yet."""
    ensure_schema()
    now = datetime.now(timezone.utc)
    sources = sorted({s for t in types for s in TYPE_SOURCES.get(t, [])})
    loaded = {}
    for source in sources:
        last = (end - timedelta(microseconds=1)).year  # [start, end): Jan 1 of the next year isn't included
        for year in range(max(start.year, FIRST_YEAR[source]), min(last, now.year) + 1):
            with _locks[(source, year)]:
                with tiger_conn() as conn:
                    row = conn.execute("SELECT loaded_at, version FROM event_coverage WHERE source = %s AND year = %s",
                                       (source, year)).fetchone()
                current_year = year == now.year
                if row and not (current_year and now - row[0] > timedelta(days=1)):
                    continue  # past years never change (NCEI revisions are picked up by the daily current-year check)
                if row and source == "noaa-storm-events":
                    found = storm_events_file(year)
                    if found and found[1] == row[1]:
                        with tiger_conn() as conn:
                            conn.execute("UPDATE event_coverage SET loaded_at = now() WHERE source = %s AND year = %s", (source, year))
                        continue
                batch, version = LOADERS[source](year)
                if batch.rows:
                    load_events(batch)
                    _anchor_and_register(batch)
                with tiger_conn() as conn:
                    conn.execute("""INSERT INTO event_coverage (source, year, loaded_at, version) VALUES (%s, %s, now(), %s)
                                    ON CONFLICT (source, year) DO UPDATE SET loaded_at = now(), version = EXCLUDED.version""",
                                 (source, year, version))
                loaded[f"{source}:{year}"] = {"batch_id": batch.batch_id, "rows": len(batch.rows)}
    return loaded


def _anchor_and_register(batch: Batch) -> None:
    # Rows are already loaded (events use their own table), so anchor + register without re-loading.
    from . import store
    from .provenance import anchor
    manifest = batch.manifest()
    store.register(batch, manifest, anchor(manifest))


def _f(v):
    return None if v is None else float(v)


def _json(obj: dict) -> str:
    # sort_keys: Postgres JSONB reorders keys, and the row hash must match what the database returns
    return json.dumps(obj, sort_keys=True)


EVENT_COLUMNS = ("source, event_id, type, name, starts_at, ends_at, lat, lon, end_lat, end_lon, magnitude, "
                 "magnitude_label, deaths, injuries, damage_usd, region, details")


def stored_event_rows(batch_id: str) -> list[tuple]:
    with tiger_conn() as conn:
        return [tuple(r[:-1]) + (_json(r[-1]) if r[-1] is not None else None,)
                for r in conn.execute(f"SELECT {EVENT_COLUMNS} FROM events WHERE batch_id = %s", (batch_id,))]


def _base(types, start, end, lat=None, lon=None, radius_km=None, min_magnitude=None, sources=None, region=None):
    """SELECT over events matching the filters, with distance_km when searching around a place.

    region = {"pattern": "%, Oklahoma", "sources": [...]}: for a state or country, records from those sources
    must also name it, so a radius drawn around Oklahoma doesn't pull in Texas.
    """
    params: list = [types, start, end]
    where = "type = ANY(%s) AND starts_at >= %s AND starts_at < %s"
    if region:
        where += " AND (source <> ALL(%s) OR region ILIKE %s)"
        params += [region["sources"], region["pattern"]]
    if min_magnitude is not None:
        where += " AND magnitude >= %s"
        params.append(min_magnitude)
    if sources:
        where += " AND source = ANY(%s)"
        params.append(sources)
    if lat is None or not radius_km:
        return f"SELECT *, NULL::double precision AS distance_km FROM events WHERE {where}", params
    # bounding box first (cheap), then exact great-circle distance
    dlat = radius_km / 111.0
    dlon = min(180.0, radius_km / max(1e-6, 111.0 * math.cos(math.radians(lat))))
    where += " AND lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s"
    params += [lat - dlat, lat + dlat, lon - dlon, lon + dlon]
    distance = ("12742 * asin(sqrt(power(sin(radians(lat - %s) / 2), 2) + "
                "cos(radians(%s)) * cos(radians(lat)) * power(sin(radians(lon - %s) / 2), 2)))")
    inner = f"SELECT *, {distance} AS distance_km FROM events WHERE {where}"
    return f"SELECT * FROM ({inner}) e WHERE distance_km <= %s", [lat, lat, lon] + params + [radius_km]


def find_events(types, start, end, lat=None, lon=None, radius_km=None, limit: int = 500, min_magnitude=None,
                sources=None, order: str = "magnitude", region=None) -> list[dict]:
    """Events of these types in [start, end), within radius_km of (lat, lon) if given."""
    ensure_schema()
    sql, args = _base(types, start, end, lat, lon, radius_km, min_magnitude, sources, region)
    order_by = {"magnitude": "magnitude DESC NULLS LAST, starts_at", "distance": "distance_km, starts_at",
                "time": "starts_at"}[order]
    with tiger_conn(row_factory=dict_row) as conn:
        return conn.execute(f"{sql} ORDER BY {order_by} LIMIT %s", args + [limit]).fetchall()


def summarize_events(types, start, end, lat=None, lon=None, radius_km=None, min_magnitude=None, sources=None,
                     region=None) -> dict:
    """Exact counts and totals (not limited like find_events): by type, by month, deaths, injuries, damage."""
    ensure_schema()
    sql, args = _base(types, start, end, lat, lon, radius_km, min_magnitude, sources, region)
    with tiger_conn(row_factory=dict_row) as conn:
        rows = conn.execute(f"""SELECT type, to_char(starts_at, 'YYYY-MM') AS month, count(*) AS n,
                                       coalesce(sum(deaths), 0) AS deaths, coalesce(sum(injuries), 0) AS injuries,
                                       coalesce(sum(damage_usd), 0) AS damage_usd,
                                       array_agg(DISTINCT batch_id) AS batches
                                FROM ({sql}) x GROUP BY 1, 2 ORDER BY 2""", args).fetchall()
    by_type: dict[str, int] = defaultdict(int)
    by_month: dict[str, int] = defaultdict(int)
    batches: set[str] = set()
    for r in rows:
        by_type[r["type"]] += r["n"]
        by_month[r["month"]] += r["n"]
        batches.update(b for b in r["batches"] if b)
    return {"count": sum(by_type.values()), "by_type": dict(by_type), "by_month": dict(by_month),
            "deaths": sum(r["deaths"] for r in rows), "injuries": sum(r["injuries"] for r in rows),
            "damage_usd": sum(float(r["damage_usd"]) for r in rows), "batch_ids": sorted(batches)}


def nearest_events(types, start, end, lat: float, lon: float, limit: int = 3, max_km: float = 500,
                   min_magnitude=None, sources=None, region=None) -> list[dict]:
    """When little is inside the radius: the closest ones, so the answer can say 'the nearest was 36 km away'."""
    return find_events(types, start, end, lat, lon, max_km, limit, min_magnitude, sources, "distance", region)


def coverage_note(source: str) -> str | None:
    """How current a lagging source is, e.g. NOAA Storm Events runs a few months behind."""
    ensure_schema()
    with tiger_conn() as conn:
        latest = conn.execute("SELECT max(starts_at) FROM events WHERE source = %s", (source,)).fetchone()[0]
    return latest.date().isoformat() if latest else None
