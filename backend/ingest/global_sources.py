"""Global modeled data for any coordinates, via Open-Meteo (no API key).

  copernicus-cams      PM2.5, ozone, NO2    hourly; Europe from 2019, worldwide from Aug 2022
  ecmwf-era5           temperature, humidity  daily reanalysis, ~5 day lag
  open-meteo-forecast  temperature, humidity  hourly, recent days (weather-model analysis)
  glofas               river discharge        daily, nearest river cell

These are model estimates, not monitor readings; every batch is labeled quality="modeled".
Units are converted to match the measured US data: ozone/NO2 µg/m³ -> ppb, discharge m³/s -> ft³/s.
"""

import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from shared.places import Place

from .provenance import Batch

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"

# µg/m³ -> ppb at 25 °C, 1 atm: ppb = µg/m³ * 24.45 / molecular weight
AIR_VARS = {"pm2_5": ("pm25", "µg/m³", 1.0), "ozone": ("o3", "ppb", 24.45 / 48.00),
            "nitrogen_dioxide": ("no2", "ppb", 24.45 / 46.01)}
CUBIC_M_TO_FT = 35.3147
AIR_HISTORY_START = date(2019, 1, 1)  # CAMS Europe; elsewhere values start 2022-08 and earlier days are empty


AREA_MIN_KM = 150  # places bigger than this (countries, states, regions) are averaged over a grid


def area_points(place: Place) -> list[tuple[float, float]]:
    """One point for a city; a 3x3 grid across the place for anything larger."""
    radius = place.radius_km or 0
    if radius <= AREA_MIN_KM:
        return [(place.lat, place.lon)]
    import math
    # Bounding boxes include outlying islands (Spain's reaches the Canaries), so sample the core: <= 450 km out.
    dlat = min(radius * 0.6, 450) / 111.0
    dlon = dlat / max(0.2, math.cos(math.radians(place.lat)))
    return [(round(place.lat + i * dlat, 3), round(((place.lon + j * dlon + 180) % 360) - 180, 3))
            for i in (-1, 0, 1) for j in (-1, 0, 1)]


def _coords(place: Place) -> dict:
    pts = area_points(place)
    return {"latitude": ",".join(str(a) for a, _ in pts), "longitude": ",".join(str(b) for _, b in pts),
            "timezone": "UTC"}


def _chunks(start: date, until: date, place: Place, years: int = 10):
    """Long ranges for area-averaged places are fetched in pieces; one request for a city."""
    if len(area_points(place)) == 1 and (until - start).days <= 366 * 30:
        yield start, until
        return
    s = start
    while s < until:
        e = min(date(s.year + years, 1, 1), until)
        yield s, e
        s = e


def _area_payload(body: bytes) -> dict:
    """A single point's payload, or the average across the land points of a multi-point request."""
    data = json.loads(body)
    if isinstance(data, dict):
        return data
    land = [d for d in data if (d.get("elevation") or 0) > 0] or data  # sea points report elevation 0
    merged = {k: v for k, v in land[0].items() if k not in ("hourly", "daily")}
    merged["area_points_used"] = len(land)
    for section in ("hourly", "daily"):
        if section not in land[0]:
            continue
        out = {"time": land[0][section]["time"]}
        for var in land[0][section]:
            if var == "time":
                continue
            columns = [d[section].get(var, []) for d in land]
            out[var] = []
            for i in range(len(out["time"])):
                vals = [c[i] for c in columns if i < len(c) and c[i] is not None]
                out[var].append(sum(vals) / len(vals) if vals else None)
        merged[section] = out
    return merged


def _hours(payload: dict, var: str):
    for stamp, value in zip(payload["hourly"]["time"], payload["hourly"][var]):
        if value is not None:
            yield datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc), float(value)


def _daily_from_hourly(place: Place, metric: str, unit: str, hours) -> list[tuple]:
    days: dict[date, list[float]] = defaultdict(list)
    for t, v in hours:
        days[t.date()].append(v)
    return [(d, place.key, metric, unit, round(statistics.fmean(vs), 4), round(min(vs), 4), round(max(vs), 4), len(vs))
            for d, vs in sorted(days.items()) if len(vs) >= 12]  # skip days with under half their hours


# ---------------------------------------------------------------- air quality (CAMS)

DUST_VARS = {"dust": ("dust", "µg/m³", 1.0)}


def cams_history(place: Place, start: date, until: date, variables: dict = AIR_VARS) -> Batch:
    what = "dust" if variables is DUST_VARS else "air quality"
    batch = Batch("copernicus-cams", f"Copernicus CAMS {what} for {place.label} {start}..{until - timedelta(days=1)}",
                  "modeled", "snowflake")
    payload = _area_payload(batch.fetch(AIR_URL, _coords(place) | {
        "hourly": ",".join(variables), "start_date": start.isoformat(), "end_date": (until - timedelta(days=1)).isoformat()}))
    for var, (metric, unit, scale) in variables.items():
        batch.rows += _daily_from_hourly(place, metric, unit, ((t, v * scale) for t, v in _hours(payload, var)))
    return batch


def cams_recent(place: Place, since: datetime, now: datetime, variables: dict = AIR_VARS) -> Batch:
    what = "dust" if variables is DUST_VARS else "air quality"
    batch = Batch("copernicus-cams", f"Copernicus CAMS {what} for {place.label} since {since:%Y-%m-%d}",
                  "modeled", "tiger")
    payload = _area_payload(batch.fetch(AIR_URL, _coords(place) | {
        "hourly": ",".join(variables), "start_date": since.date().isoformat(), "end_date": now.date().isoformat()}))
    for var, (metric, unit, scale) in variables.items():
        batch.rows += [(t, place.key, metric, round(v * scale, 4), unit) for t, v in _hours(payload, var) if since <= t <= now]
    return batch


# ---------------------------------------------------------------- weather (ERA5 + recent model analysis)

def era5_history(place: Place, start: date, until: date) -> Batch:
    batch = Batch("ecmwf-era5", f"ECMWF ERA5 daily weather for {place.label} {start}..{until - timedelta(days=1)}",
                  "modeled", "snowflake")
    parts = [_area_payload(batch.fetch(ARCHIVE_URL, _coords(place) | {
        "start_date": s.isoformat(), "end_date": (e - timedelta(days=1)).isoformat(),
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,"
                 "relative_humidity_2m_mean,relative_humidity_2m_max,relative_humidity_2m_min"}))
        for s, e in _chunks(start, until, place)]
    d = {k: [v for part in parts for v in part["daily"][k]] for k in parts[0]["daily"]}
    # Cast to float: the API returns whole numbers as ints, and the row hash must match what the DB returns.
    f = lambda key, i: round(float(d[key][i]), 4)
    for i, stamp in enumerate(d["time"]):
        day = date.fromisoformat(stamp)
        if None not in (d["temperature_2m_mean"][i], d["temperature_2m_min"][i], d["temperature_2m_max"][i]):
            batch.rows.append((day, place.key, "temperature", "°C", f("temperature_2m_mean", i),
                               f("temperature_2m_min", i), f("temperature_2m_max", i), 24))
        if None not in (d["relative_humidity_2m_mean"][i], d["relative_humidity_2m_min"][i], d["relative_humidity_2m_max"][i]):
            batch.rows.append((day, place.key, "humidity", "%", f("relative_humidity_2m_mean", i),
                               f("relative_humidity_2m_min", i), f("relative_humidity_2m_max", i), 24))
    return batch


def weather_recent(place: Place, since: datetime, now: datetime, days: int) -> Batch:
    batch = Batch("open-meteo-forecast", f"Open-Meteo weather-model analysis for {place.label} since {since:%Y-%m-%d}",
                  "modeled", "tiger")
    payload = _area_payload(batch.fetch(FORECAST_URL, _coords(place) | {
        "hourly": "temperature_2m,relative_humidity_2m", "past_days": days + 1, "forecast_days": 1}))
    for var, metric, unit in (("temperature_2m", "temperature", "°C"), ("relative_humidity_2m", "humidity", "%")):
        batch.rows += [(t, place.key, metric, round(v, 4), unit) for t, v in _hours(payload, var) if since <= t <= now]
    return batch


# ---------------------------------------------------------------- rain (ERA5 daily totals, 1940 ->)

def rain_history(place: Place, start: date, until: date) -> Batch:
    batch = Batch("ecmwf-era5", f"ECMWF ERA5 daily precipitation for {place.label} {start}..{until - timedelta(days=1)}",
                  "modeled", "snowflake")
    parts = [_area_payload(batch.fetch(ARCHIVE_URL, _coords(place) | {
        "start_date": s.isoformat(), "end_date": (e - timedelta(days=1)).isoformat(), "daily": "precipitation_sum"}))
        for s, e in _chunks(start, until, place)]
    d = {k: [v for part in parts for v in part["daily"][k]] for k in parts[0]["daily"]}
    for stamp, v in zip(d["time"], d["precipitation_sum"]):
        if v is not None:
            v = round(float(v), 4)
            batch.rows.append((date.fromisoformat(stamp), place.key, "precipitation", "mm/day", v, v, v, 1))
    return batch


def rain_recent(place: Place, since: datetime, now: datetime, days: int) -> Batch:
    """Daily totals (one row per day), so Tiger's daily averages stay equal to the day's total."""
    batch = Batch("open-meteo-forecast", f"Open-Meteo daily precipitation for {place.label} since {since:%Y-%m-%d}",
                  "modeled", "tiger")
    payload = _area_payload(batch.fetch(FORECAST_URL, _coords(place) | {
        "daily": "precipitation_sum", "past_days": days + 1, "forecast_days": 1}))
    d = payload["daily"]
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for stamp, v in zip(d["time"], d["precipitation_sum"]):
        t = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        if v is not None and since <= t < today:  # completed days only
            batch.rows.append((t, place.key, "precipitation", round(float(v), 4), "mm/day"))
    return batch


# ---------------------------------------------------------------- rivers (GloFAS)

_river_cells: dict[str, tuple[float, float]] = {}


def river_cell(place: Place) -> tuple[float, float]:
    """The main river near a place: the GloFAS cell with the largest recent flow within ~22 km.

    The cell nearest a city's center is often a tiny channel (Cairo's is ~16 ft³/s, not the Nile), so
    sample a 9x9 grid at GloFAS's 0.05° resolution and pick the biggest. Remembered in the places table.
    """
    if place.key in _river_cells:
        return _river_cells[place.key]
    from ingest.store import tiger_conn
    with tiger_conn() as conn:
        conn.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS river_lat DOUBLE PRECISION")
        conn.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS river_lon DOUBLE PRECISION")
        row = conn.execute("SELECT river_lat, river_lon FROM places WHERE key = %s", (place.key,)).fetchone()
    if row and row[0] is not None:
        _river_cells[place.key] = (row[0], row[1])
        return _river_cells[place.key]
    grid = [(round(place.lat + dy * 0.05, 3), round(place.lon + dx * 0.05, 3)) for dy in range(-4, 5) for dx in range(-4, 5)]
    import httpx
    resp = httpx.get(FLOOD_URL, params={"latitude": ",".join(str(a) for a, _ in grid),
                                        "longitude": ",".join(str(b) for _, b in grid),
                                        "daily": "river_discharge", "past_days": 30, "forecast_days": 1}, timeout=90)
    resp.raise_for_status()
    best, best_flow = (place.lat, place.lon), -1.0
    for (lat, lon), cell in zip(grid, resp.json()):
        flows = [v for v in cell["daily"]["river_discharge"] if v is not None]
        if flows and statistics.fmean(flows) > best_flow:
            best, best_flow = (lat, lon), statistics.fmean(flows)
    with tiger_conn() as conn:
        conn.execute("UPDATE places SET river_lat = %s, river_lon = %s WHERE key = %s", (best[0], best[1], place.key))
    _river_cells[place.key] = best
    return best


def glofas(place: Place, start: date, until: date, store: str) -> Batch:
    batch = Batch("glofas", f"GloFAS river discharge near {place.label} {start}..{until - timedelta(days=1)}",
                  "modeled", store)
    lat, lon = river_cell(place)
    payload = json.loads(batch.fetch(FLOOD_URL, {"latitude": lat, "longitude": lon,
                                                 "daily": "river_discharge", "start_date": start.isoformat(),
                                                 "end_date": (until - timedelta(days=1)).isoformat()}))
    for stamp, value in zip(payload["daily"]["time"], payload["daily"]["river_discharge"]):
        if value is None:
            continue
        day, flow = date.fromisoformat(stamp), round(float(value) * CUBIC_M_TO_FT, 4)
        if store == "tiger":
            batch.rows.append((datetime(day.year, day.month, day.day, tzinfo=timezone.utc), place.key, "streamflow", flow, "ft³/s"))
        else:
            batch.rows.append((day, place.key, "streamflow", "ft³/s", flow, flow, flow, 1))
    return batch
