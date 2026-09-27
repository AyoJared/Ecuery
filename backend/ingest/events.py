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
    "hurricane": "Tropical cyclone (hurricane / typhoon)", "winter_storm": "Winter storm", "heat": "Extreme heat",
    "wildfire": "Wildfire", "drought": "Drought", "earthquake": "Earthquake", "volcano": "Volcanic eruption",
    "landslide": "Landslide", "severe_storm": "Severe storm",
}
# Which sources can answer which types (US-only types come from NOAA Storm Events).
TYPE_SOURCES = {
    "tornado": ["noaa-storm-events"], "hail": ["noaa-storm-events"], "thunderstorm_wind": ["noaa-storm-events"],
    # Floods/droughts: NOAA for the US, GDACS worldwide (EONET's flood list is sparse and would double count).
    "flood": ["noaa-storm-events", "gdacs"], "drought": ["noaa-storm-events", "gdacs"],
    # One record per storm with its whole track (NOAA/EONET list county impacts / snapshots and would double count).
    "hurricane": ["ibtracs"],
    "winter_storm": ["noaa-storm-events"], "heat": ["noaa-storm-events"],
    "wildfire": ["noaa-storm-events", "nasa-eonet"], "earthquake": ["usgs-earthquakes"],
    "volcano": ["nasa-eonet"], "landslide": ["noaa-storm-events", "nasa-eonet"], "severe_storm": ["nasa-eonet"],
}
# Earthquake deaths and damage live in NOAA's significant-earthquake database (USGS lists no casualties).
IMPACT_SOURCES = {"earthquake": ["noaa-sig-earthquakes"]}

BASINS = {"NA": "North Atlantic", "EP": "Eastern Pacific", "WP": "Western Pacific", "NI": "North Indian Ocean",
          "SI": "South Indian Ocean", "SP": "South Pacific", "SA": "South Atlantic", "MM": "Unknown basin"}
BASIN_ALIASES = {
    "north atlantic": ["NA"], "atlantic": ["NA", "SA"], "atlantic ocean": ["NA", "SA"], "caribbean": ["NA"],
    "gulf of mexico": ["NA"], "eastern pacific": ["EP"], "east pacific": ["EP"], "northeast pacific": ["EP"],
    "western pacific": ["WP"], "west pacific": ["WP"], "northwest pacific": ["WP"], "pacific": ["WP", "EP", "SP"],
    "indian ocean": ["NI", "SI"], "north indian ocean": ["NI"], "bay of bengal": ["NI"], "arabian sea": ["NI"],
    "south indian ocean": ["SI"], "south pacific": ["SP"], "southern hemisphere": ["SI", "SP", "SA"],
}


def basin_codes(name: str) -> list[str] | None:
    key = name.lower().replace(",", " ").replace("ocean ocean", "ocean").strip()
    key = " ".join(w for w in key.split() if w not in ("the", "basin", "region"))
    return BASIN_ALIASES.get(key)

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
    """CREATE TABLE IF NOT EXISTS storm_track (
        sid TEXT NOT NULL, time TIMESTAMPTZ NOT NULL, lat DOUBLE PRECISION NOT NULL, lon DOUBLE PRECISION NOT NULL,
        wind_kt DOUBLE PRECISION, PRIMARY KEY (sid, time))""",
    "CREATE INDEX IF NOT EXISTS storm_track_latlon ON storm_track (lat, lon)",
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

def usgs_earthquakes(year: int):
    if year < 1990:
        return usgs_archive()
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


def usgs_archive():
    """1900-1989 at M5.5+ (the catalog is only complete for large quakes that far back), loaded once."""
    batch = Batch("usgs-earthquakes", "USGS ComCat earthquakes M5.5+ worldwide 1900-1989", "official", "events")
    for decade in range(1900, 1990, 10):
        body = batch.fetch("https://earthquake.usgs.gov/fdsnws/event/1/query", {
            "format": "geojson", "starttime": f"{decade}-01-01", "endtime": f"{decade + 10}-01-01",
            "minmagnitude": 5.5, "eventtype": "earthquake", "orderby": "time-asc"})
        for f in json.loads(body)["features"]:
            p_, (lon, lat, depth) = f["properties"], f["geometry"]["coordinates"][:3]
            t = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=p_["time"])  # pre-1970 safe on Windows
            batch.rows.append(("usgs-earthquakes", f["id"], "earthquake", p_.get("title"), t, None, _f(lat), _f(lon), None,
                               None, _f(p_.get("mag")), f"M{p_['mag']}" if p_.get("mag") is not None else None, None, None,
                               None, p_.get("place"), _json({"depth_km": _f(depth), "tsunami": p_.get("tsunami"),
                                                              "alert": p_.get("alert"), "url": p_.get("url")})))
    return batch, datetime.now(timezone.utc).date().isoformat(), list(range(1900, 1990))


# ---------------------------------------------------------------- NOAA significant earthquakes (deaths, damage)

def noaa_sig_earthquakes(year: int):
    """NOAA NCEI/WDS Significant Earthquake Database: ~4,000 damaging/deadly quakes since 1900, loaded once."""
    batch = Batch("noaa-sig-earthquakes", "NOAA NCEI Significant Earthquake Database 1900 ->", "official", "events")
    now = datetime.now(timezone.utc)
    page, pages = 1, 1
    while page <= pages:
        data = json.loads(batch.fetch("https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/earthquakes",
                                      {"minYear": 1900, "maxYear": now.year, "page": page}))
        pages = data.get("totalPages", 1)
        for q in data.get("items", []):
            if q.get("latitude") is None or not q.get("year"):
                continue
            t = datetime(int(q["year"]), int(q.get("month") or 1), int(q.get("day") or 1), int(q.get("hour") or 0),
                         int(q.get("minute") or 0), tzinfo=timezone.utc)
            mag = q.get("eqMagnitude") or q.get("eqMagMw") or q.get("eqMagMs")
            deaths = q.get("deathsTotal") if q.get("deathsTotal") is not None else q.get("deaths")
            batch.rows.append(("noaa-sig-earthquakes", str(q["id"]), "earthquake", q.get("locationName"), t, None,
                               _f(q["latitude"]), _f(q["longitude"]), None, None, _f(mag),
                               f"M{mag}" if mag is not None else None, int(deaths) if deaths is not None else None,
                               None, None, (q.get("country") or "").title() or None,
                               _json({"damage_scale": q.get("damageAmountOrderTotal"), "intensity": q.get("intensity"),
                                      "depth_km": _f(q.get("eqDepth"))})))
        page += 1
    return batch, now.date().isoformat(), list(range(1900, now.year + 1))


# ---------------------------------------------------------------- GDACS floods and droughts (worldwide, 2001 ->)

def gdacs(year: int):
    batch = Batch("gdacs", f"GDACS flood and drought alerts {year}", "official", "events")
    today = datetime.now(timezone.utc).date()
    body = batch.fetch("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH", {
        "eventlist": "FL;DR", "fromdate": f"{year}-01-01", "todate": min(date(year, 12, 31), today).isoformat(),
        "alertlevel": "Green;Orange;Red"})
    features = json.loads(body).get("features", []) if body.strip() else []
    level = {"Green": 1.0, "Orange": 2.0, "Red": 3.0}
    for f in features:
        p_ = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        kind = "flood" if p_["eventtype"] == "FL" else "drought"
        batch.rows.append(("gdacs", f"{p_['eventtype']}{p_['eventid']}", kind, p_.get("name"),
                           datetime.fromisoformat(p_["fromdate"]).replace(tzinfo=timezone.utc),
                           datetime.fromisoformat(p_["todate"]).replace(tzinfo=timezone.utc) if p_.get("todate") else None,
                           _f(lat), _f(lon), None, None, level.get(p_.get("alertlevel")), f"{p_.get('alertlevel')} alert",
                           None, None, None, p_.get("country"),
                           _json({"alertlevel": p_.get("alertlevel"), "iso3": p_.get("iso3"),
                                  "url": (p_.get("url") or {}).get("report") if isinstance(p_.get("url"), dict) else None})))
    return batch, today.isoformat()


# ---------------------------------------------------------------- IBTrACS tropical cyclones (worldwide, 1980 ->)

IBTRACS = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/"


def _saffir_simpson(kt: float | None) -> str:
    if kt is None:
        return "unknown"
    for limit, label in ((137, "Category 5"), (113, "Category 4"), (96, "Category 3"), (83, "Category 2"),
                         (64, "Category 1"), (34, "Tropical storm")):
        if kt >= limit:
            return label
    return "Tropical depression"


def ibtracs(year: int):
    """One event per storm (peak wind, pressure, fastest 24 h strengthening, duration) plus its 6-hourly track."""
    import csv as _csv
    now = datetime.now(timezone.utc)
    recent = year >= now.year - 2
    name = "ibtracs.last3years.list.v04r01.csv" if recent else "ibtracs.since1980.list.v04r01.csv"
    years = list(range(now.year - 2, now.year + 1)) if recent else list(range(1980, now.year - 2))
    batch = Batch("ibtracs", f"NOAA IBTrACS v04r01 tropical cyclones ({'last 3 seasons' if recent else '1980 ->'})",
                  "official", "events")
    text = batch.fetch(IBTRACS + name).decode("utf-8", "replace")
    reader = _csv.reader(io.StringIO(text))
    header = next(reader)
    next(reader)  # units row
    col = {c: i for i, c in enumerate(header)}
    storms: dict[str, list] = defaultdict(list)
    for r in reader:
        if r[col["TRACK_TYPE"]] != "main":
            continue  # provisional spurs
        storms[r[col["SID"]]].append(r)
    num = lambda r, c: float(r[col[c]]) if r[col[c]].strip() else None
    batch.tracks = []
    for sid, pts in storms.items():
        pts.sort(key=lambda r: r[col["ISO_TIME"]])
        seasons = {int(r[col["SEASON"]]) for r in pts}
        if recent and not seasons & set(years):
            continue
        times = [datetime.fromisoformat(r[col["ISO_TIME"]]).replace(tzinfo=timezone.utc) for r in pts]
        winds = [num(r, "USA_WIND") if num(r, "USA_WIND") is not None else num(r, "WMO_WIND") for r in pts]
        pres = [num(r, "USA_PRES") if num(r, "USA_PRES") is not None else num(r, "WMO_PRES") for r in pts]
        known = [(t, w) for t, w in zip(times, winds) if w is not None]
        peak_i = max(range(len(pts)), key=lambda i: winds[i] if winds[i] is not None else -1)
        by_time = dict(known)
        rapid = max((by_time[t + timedelta(hours=24)] - w for t, w in known if t + timedelta(hours=24) in by_time),
                    default=None)
        peak = winds[peak_i]
        basin = pts[peak_i][col["BASIN"]]
        storm_name = pts[0][col["NAME"]].title()
        season = max(seasons)
        batch.rows.append((
            "ibtracs", sid, "hurricane", f"{storm_name if storm_name != 'Not_Named' else 'Unnamed storm'} ({season})",
            times[0], times[-1], _f(pts[peak_i][col["LAT"]]), _f(pts[peak_i][col["LON"]]),
            _f(pts[-1][col["LAT"]]), _f(pts[-1][col["LON"]]), _f(peak),
            f"{_saffir_simpson(peak)}, {int(peak)} kt" if peak is not None else None, None, None, None,
            BASINS.get(basin, basin),
            _json({"basin": basin, "season": season, "sshs_peak": _saffir_simpson(peak),
                   "min_pressure_mb": _f(min((p for p in pres if p is not None), default=None)),
                   "max_intensification_24h_kt": _f(rapid),
                   "duration_days": round((times[-1] - times[0]).total_seconds() / 86400, 2),
                   "named": storm_name != "Not_Named"})))
        for t, r, w in zip(times, pts, winds):
            if t.hour % 6 == 0 and t.minute == 0:
                batch.tracks.append((sid, t, float(r[col["LAT"]]), float(r[col["LON"]]), w))
    return batch, now.date().isoformat(), years


def load_tracks(batch: Batch) -> None:
    rows = list({(r[0], r[1]): r for r in getattr(batch, "tracks", [])}.values())
    if not rows:
        return
    with tiger_conn() as conn, conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE track_staging (LIKE storm_track) ON COMMIT DROP")
        with cur.copy("COPY track_staging (sid, time, lat, lon, wind_kt) FROM STDIN") as copy:
            for r in rows:
                copy.write_row(r)
        cur.execute("""INSERT INTO storm_track SELECT * FROM track_staging ON CONFLICT (sid, time)
                       DO UPDATE SET lat = EXCLUDED.lat, lon = EXCLUDED.lon, wind_kt = EXCLUDED.wind_kt""")


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

LOADERS = {"noaa-storm-events": noaa_storm_events, "usgs-earthquakes": usgs_earthquakes, "nasa-eonet": nasa_eonet,
           "ibtracs": ibtracs, "gdacs": gdacs, "noaa-sig-earthquakes": noaa_sig_earthquakes}
FIRST_YEAR = {"noaa-storm-events": 1996, "usgs-earthquakes": 1900, "nasa-eonet": 2017, "ibtracs": 1980, "gdacs": 2001,
              "noaa-sig-earthquakes": 1900}


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


def ensure_events(types: list[str], start: datetime, end: datetime, sources: list[str] | None = None) -> dict:
    """Load every source-year the question needs that isn't loaded (or is stale) yet."""
    ensure_schema()
    now = datetime.now(timezone.utc)
    sources = sorted(set(sources) if sources else {s for t in types for s in TYPE_SOURCES.get(t, [])})
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
                result = LOADERS[source](year)
                batch, version = result[0], result[1]
                covered = result[2] if len(result) > 2 else [year]  # archives cover many years in one file
                if batch.rows:
                    load_events(batch)
                    load_tracks(batch)
                    _anchor_and_register(batch)
                with tiger_conn() as conn, conn.cursor() as cur:
                    cur.executemany("""INSERT INTO event_coverage (source, year, loaded_at, version) VALUES (%s, %s, now(), %s)
                                       ON CONFLICT (source, year) DO UPDATE SET loaded_at = now(), version = EXCLUDED.version""",
                                    [(source, y, version) for y in covered])
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


DIST = ("12742 * asin(sqrt(power(sin(radians({t}.lat - %s) / 2), 2) + "
        "cos(radians(%s)) * cos(radians({t}.lat)) * power(sin(radians({t}.lon - %s) / 2), 2)))")


def _base(types, start, end, lat=None, lon=None, radius_km=None, min_magnitude=None, sources=None, region=None,
          basins=None, name=None):
    """SELECT over events matching the filters, with distance_km when searching around a place.

    Tropical cyclones (ibtracs) match a place if any point of their TRACK passed within the radius, and their
    distance is the closest approach. region = {"pattern": "%, Oklahoma", "sources": [...]} keeps state/country
    searches inside their borders for sources that name them.
    """
    params: list = [types, start, end]
    where = "e.type = ANY(%s) AND e.starts_at >= %s AND e.starts_at < %s"
    if min_magnitude is not None:
        where += " AND e.magnitude >= %s"
        params.append(min_magnitude)
    if sources:
        where += " AND e.source = ANY(%s)"
        params.append(sources)
    if region:
        where += " AND (e.source <> ALL(%s) OR e.region ILIKE %s)"
        params += [region["sources"], region["pattern"]]
    if basins:
        where += " AND e.details->>'basin' = ANY(%s)"
        params.append(basins)
    if name:
        where += " AND e.name ILIKE %s"
        params.append(f"%{name}%")
    if lat is None or not radius_km:
        return f"SELECT e.*, NULL::double precision AS distance_km FROM events e WHERE {where}", params
    dlat = radius_km / 111.0
    dlon = min(180.0, radius_km / max(1e-6, 111.0 * math.cos(math.radians(lat))))
    box = [lat - dlat, lat + dlat, lon - dlon, lon + dlon]
    sql = f"""SELECT e.*, CASE WHEN e.source = 'ibtracs' THEN tr.d ELSE {DIST.format(t='e')} END AS distance_km
              FROM events e
              LEFT JOIN LATERAL (SELECT min({DIST.format(t='st')}) AS d FROM storm_track st
                                 WHERE e.source = 'ibtracs' AND st.sid = e.event_id
                                   AND st.lat BETWEEN %s AND %s AND st.lon BETWEEN %s AND %s) tr ON TRUE
              WHERE {where} AND (e.source = 'ibtracs' OR (e.lat BETWEEN %s AND %s AND e.lon BETWEEN %s AND %s))"""
    args = [lat, lat, lon] + [lat, lat, lon] + box + params + box
    return f"SELECT * FROM ({sql}) x WHERE distance_km <= %s", args + [radius_km]


ORDER = {
    "magnitude": "magnitude DESC NULLS LAST, starts_at",
    "intensification": "(details->>'max_intensification_24h_kt')::float DESC NULLS LAST, magnitude DESC NULLS LAST",
    "duration": "(details->>'duration_days')::float DESC NULLS LAST",
    "deaths": "deaths DESC NULLS LAST, magnitude DESC NULLS LAST",
    "damage": "damage_usd DESC NULLS LAST, (details->>'damage_scale')::float DESC NULLS LAST",
    "distance": "distance_km, starts_at",
    "time": "starts_at",
}


def find_events(types, start, end, lat=None, lon=None, radius_km=None, limit: int = 500, min_magnitude=None,
                sources=None, order: str = "magnitude", region=None, basins=None, name=None) -> list[dict]:
    """Events of these types in [start, end), within radius_km of (lat, lon) if given."""
    ensure_schema()
    sql, args = _base(types, start, end, lat, lon, radius_km, min_magnitude, sources, region, basins, name)
    with tiger_conn(row_factory=dict_row) as conn:
        return conn.execute(f"{sql} ORDER BY {ORDER[order]} LIMIT %s", args + [limit]).fetchall()


def summarize_events(types, start, end, lat=None, lon=None, radius_km=None, min_magnitude=None, sources=None,
                     region=None, basins=None, name=None) -> dict:
    """Exact counts and totals (not limited like find_events): by type, month and year, deaths, injuries, damage."""
    ensure_schema()
    sql, args = _base(types, start, end, lat, lon, radius_km, min_magnitude, sources, region, basins, name)
    with tiger_conn(row_factory=dict_row) as conn:
        rows = conn.execute(f"""SELECT type, to_char(starts_at, 'YYYY-MM') AS month, count(*) AS n,
                                       coalesce(sum(deaths), 0) AS deaths, coalesce(sum(injuries), 0) AS injuries,
                                       coalesce(sum(damage_usd), 0) AS damage_usd,
                                       array_agg(DISTINCT batch_id) AS batches
                                FROM ({sql}) x GROUP BY 1, 2 ORDER BY 2""", args).fetchall()
        years = conn.execute(f"""SELECT extract(year FROM starts_at)::int AS year, count(*) AS count,
                                        round(avg(magnitude)::numeric, 2)::float AS mean_magnitude,
                                        max(magnitude) AS max_magnitude,
                                        round(avg(lat)::numeric, 2)::float AS mean_lat,
                                        round(avg(lon)::numeric, 2)::float AS mean_lon,
                                        round(avg((details->>'duration_days')::float)::numeric, 2)::float AS mean_duration_days,
                                        coalesce(sum(deaths), 0) AS deaths
                                 FROM ({sql}) x GROUP BY 1 ORDER BY 1""", args).fetchall()
    by_type: dict[str, int] = defaultdict(int)
    by_month: dict[str, int] = defaultdict(int)
    batches: set[str] = set()
    for r in rows:
        by_type[r["type"]] += r["n"]
        by_month[r["month"]] += r["n"]
        batches.update(b for b in r["batches"] if b)
    return {"count": sum(by_type.values()), "by_type": dict(by_type), "by_month": dict(by_month),
            "by_year": [dict(y) for y in years],
            "deaths": sum(r["deaths"] for r in rows), "injuries": sum(r["injuries"] for r in rows),
            "damage_usd": sum(float(r["damage_usd"]) for r in rows), "batch_ids": sorted(batches)}


def nearest_events(types, start, end, lat: float, lon: float, limit: int = 3, max_km: float = 500,
                   min_magnitude=None, sources=None, region=None, basins=None, name=None) -> list[dict]:
    """When little is inside the radius: the closest ones, so the answer can say 'the nearest was 36 km away'."""
    return find_events(types, start, end, lat, lon, max_km, limit, min_magnitude, sources, "distance", region, basins, name)


def coverage_note(source: str) -> str | None:
    """How current a lagging source is, e.g. NOAA Storm Events runs a few months behind."""
    ensure_schema()
    with tiger_conn() as conn:
        latest = conn.execute("SELECT max(starts_at) FROM events WHERE source = %s", (source,)).fetchone()[0]
    return latest.date().isoformat() if latest else None
