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


def _coords(place: Place) -> dict:
    return {"latitude": place.lat, "longitude": place.lon, "timezone": "UTC"}


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

def cams_history(place: Place, start: date, until: date) -> Batch:
    batch = Batch("copernicus-cams", f"Copernicus CAMS air quality for {place.label} {start}..{until - timedelta(days=1)}",
                  "modeled", "snowflake")
    payload = json.loads(batch.fetch(AIR_URL, _coords(place) | {
        "hourly": ",".join(AIR_VARS), "start_date": start.isoformat(), "end_date": (until - timedelta(days=1)).isoformat()}))
    for var, (metric, unit, scale) in AIR_VARS.items():
        batch.rows += _daily_from_hourly(place, metric, unit, ((t, v * scale) for t, v in _hours(payload, var)))
    return batch


def cams_recent(place: Place, since: datetime, now: datetime) -> Batch:
    batch = Batch("copernicus-cams", f"Copernicus CAMS air quality for {place.label} since {since:%Y-%m-%d}",
                  "modeled", "tiger")
    payload = json.loads(batch.fetch(AIR_URL, _coords(place) | {
        "hourly": ",".join(AIR_VARS), "start_date": since.date().isoformat(), "end_date": now.date().isoformat()}))
    for var, (metric, unit, scale) in AIR_VARS.items():
        batch.rows += [(t, place.key, metric, round(v * scale, 4), unit) for t, v in _hours(payload, var) if since <= t <= now]
    return batch


# ---------------------------------------------------------------- weather (ERA5 + recent model analysis)

def era5_history(place: Place, start: date, until: date) -> Batch:
    batch = Batch("ecmwf-era5", f"ECMWF ERA5 daily weather for {place.label} {start}..{until - timedelta(days=1)}",
                  "modeled", "snowflake")
    payload = json.loads(batch.fetch(ARCHIVE_URL, _coords(place) | {
        "start_date": start.isoformat(), "end_date": (until - timedelta(days=1)).isoformat(),
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,"
                 "relative_humidity_2m_mean,relative_humidity_2m_max,relative_humidity_2m_min"}))
    d = payload["daily"]
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
    payload = json.loads(batch.fetch(FORECAST_URL, _coords(place) | {
        "hourly": "temperature_2m,relative_humidity_2m", "past_days": days + 1, "forecast_days": 1}))
    for var, metric, unit in (("temperature_2m", "temperature", "°C"), ("relative_humidity_2m", "humidity", "%")):
        batch.rows += [(t, place.key, metric, round(v, 4), unit) for t, v in _hours(payload, var) if since <= t <= now]
    return batch


# ---------------------------------------------------------------- rivers (GloFAS)

def glofas(place: Place, start: date, until: date, store: str) -> Batch:
    batch = Batch("glofas", f"GloFAS river discharge near {place.label} {start}..{until - timedelta(days=1)}",
                  "modeled", store)
    payload = json.loads(batch.fetch(FLOOD_URL, {"latitude": place.lat, "longitude": place.lon,
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
