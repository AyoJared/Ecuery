"""Connectors for the agencies. Each returns a Batch of normalized rows.

Recent rows (Tiger):     (time_utc, location, metric, value, unit)
History rows (Snowflake): (day, location, metric, unit, avg, min, max, samples)

City values are the mean across that city's official monitors (see shared/catalog.py).
"""

import csv
import io
import json
import math
import statistics
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import httpx

from shared.catalog import CITIES, GLOBAL

from .provenance import Batch

COUNTY_TO_CITY = {county: c.key for c in CITIES.values() for county in c.counties}


def _daily_row(day: date, city: str, metric: str, unit: str, avgs: list[float], mins: list[float],
               maxes: list[float], samples: int) -> tuple:
    return (day, city, metric, unit, round(statistics.fmean(avgs), 4), round(min(mins), 4), round(max(maxes), 4), int(samples))


# ---------------------------------------------------------------- EPA AQS (quality-assured history)

AQS = {  # metric: (parameter code, pollutant standard to keep, multiplier to our unit, unit)
    "pm25": ("88101", "PM25 24-hour 2012", 1.0, "µg/m³"),
    "o3": ("44201", "Ozone 8-hour 2015", 1000.0, "ppb"),   # AQS reports ozone in ppm
    "no2": ("42602", "NO2 1-hour 2010", 1.0, "ppb"),
}


def epa_aqs(metric: str, start: date, until: date) -> Batch:
    code, standard, scale, unit = AQS[metric]
    batch = Batch("epa-aqs", f"EPA AQS daily {metric} (param {code}), {start}..{until - timedelta(days=1)}",
                  "quality-assured", "snowflake")
    # (city, day) -> site -> (mean, max, n); Included exceptional-event rows (e.g. smoke) win over None.
    by_day: dict[tuple, dict] = defaultdict(dict)
    for year in range(start.year, until.year + 1):
        try:
            body = batch.fetch(f"https://aqs.epa.gov/aqsweb/airdata/daily_{code}_{year}.zip")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                continue  # year not published yet
            raise
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            for r in csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), "utf-8")):
                city = COUNTY_TO_CITY.get(r["State Code"] + r["County Code"])
                if not city or r["Pollutant Standard"] != standard or r["Event Type"] == "Excluded":
                    continue
                day = date.fromisoformat(r["Date Local"])
                if not (start <= day < until) or not r["Arithmetic Mean"]:
                    continue
                site = (r["Site Num"], r["POC"])
                if site in by_day[(city, day)] and r["Event Type"] != "Included":
                    continue
                by_day[(city, day)][site] = (float(r["Arithmetic Mean"]) * scale,
                                             float(r["1st Max Value"] or r["Arithmetic Mean"]) * scale,
                                             int(r["Observation Count"] or 0))
    for (city, day), sites in sorted(by_day.items()):
        v = list(sites.values())
        batch.rows.append(_daily_row(day, city, metric, unit, [x[0] for x in v], [x[0] for x in v],
                                     [x[1] for x in v], sum(x[2] for x in v)))
    return batch


# ---------------------------------------------------------------- EPA AirNow (preliminary, real-time)

AIRNOW_HOURLY = {"PM2.5": "pm25", "OZONE": "o3", "NO2": "no2"}
AIRNOW_DAILY = {"PM2.5-24hr": "pm25", "OZONE-8HR": "o3"}  # AirNow daily files have no NO2
UNITS = {"pm25": "µg/m³", "o3": "ppb", "no2": "ppb"}


def epa_airnow_daily(start: date, until: date, skip: set[tuple] = frozenset()) -> Batch:
    """Fills the gap between the end of AQS and the recent window. `skip` = (city, metric, day) already covered."""
    batch = Batch("epa-airnow", f"EPA AirNow daily files {start}..{until - timedelta(days=1)} (PM2.5, ozone)",
                  "preliminary", "snowflake")
    days = [start + timedelta(days=i) for i in range((until - start).days)]

    def get(day: date):
        try:
            return day, batch.fetch(f"https://files.airnowtech.org/airnow/{day:%Y}/{day:%Y%m%d}/daily_data.dat")
        except httpx.HTTPStatusError:
            return day, b""

    with ThreadPoolExecutor(8) as pool:
        files = list(pool.map(get, days))
    for day, body in files:
        values: dict[tuple, list[float]] = defaultdict(list)
        for line in body.decode("utf-8", "replace").splitlines():
            f = line.split("|")
            if len(f) < 7 or f[3] not in AIRNOW_DAILY:
                continue
            city = COUNTY_TO_CITY.get(f[1][:5])
            metric = AIRNOW_DAILY[f[3]]
            if city and (city, metric, day) not in skip:
                try:
                    values[(city, metric)].append(float(f[5]))
                except ValueError:
                    pass
        for (city, metric), vs in sorted(values.items()):
            batch.rows.append(_daily_row(day, city, metric, UNITS[metric], vs, vs, vs, len(vs)))
    return batch


def epa_airnow_hourly(since: datetime, until: datetime) -> Batch:
    batch = Batch("epa-airnow", f"EPA AirNow hourly files {since:%Y-%m-%d %H}:00..{until:%Y-%m-%d %H}:00 UTC",
                  "preliminary", "tiger")
    hours = []
    t = since.replace(minute=0, second=0, microsecond=0)
    while t < until:
        hours.append(t)
        t += timedelta(hours=1)

    def get(hour: datetime):
        try:
            return hour, batch.fetch(f"https://files.airnowtech.org/airnow/{hour:%Y}/{hour:%Y%m%d}/HourlyData_{hour:%Y%m%d%H}.dat")
        except httpx.HTTPStatusError:
            return hour, b""  # latest hour not published yet

    with ThreadPoolExecutor(8) as pool:
        files = list(pool.map(get, hours))
    for hour, body in files:
        values: dict[tuple, list[float]] = defaultdict(list)
        for line in body.decode("utf-8", "replace").splitlines():
            f = line.split("|")
            if len(f) < 8 or f[5] not in AIRNOW_HOURLY:
                continue
            city = COUNTY_TO_CITY.get(f[2][:5])
            if city:
                try:
                    values[(city, AIRNOW_HOURLY[f[5]])].append(float(f[7]))
                except ValueError:
                    pass
        for (city, metric), vs in sorted(values.items()):
            batch.rows.append((hour, city, metric, round(statistics.fmean(vs), 4), UNITS[metric]))
    return batch


# ---------------------------------------------------------------- NOAA

def noaa_nws(since: datetime) -> Batch:
    """Live airport observations: temperature and relative humidity."""
    batch = Batch("noaa-nws", f"NOAA NWS station observations since {since:%Y-%m-%d %H:%M} UTC", "preliminary", "tiger")
    # The API returns at most 500 observations per call and airports report every ~5 minutes,
    # so ask for one day at a time.
    now = datetime.now(timezone.utc)
    windows = []
    t = since
    while t < now:
        windows.append((t, min(t + timedelta(days=1), now)))
        t += timedelta(days=1)
    features = []
    for city in CITIES.values():
        for start, end in windows:
            body = batch.fetch(f"https://api.weather.gov/stations/{city.nws_station}/observations",
                               {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "limit": 500})
            features += [(city, f) for f in json.loads(body).get("features", [])]
    for city, feature in features:
        p = feature["properties"]
        t = datetime.fromisoformat(p["timestamp"]).astimezone(timezone.utc)
        temp = (p.get("temperature") or {}).get("value")
        rh = (p.get("relativeHumidity") or {}).get("value")
        if temp is not None:
            batch.rows.append((t, city.key, "temperature", round(float(temp), 4), "°C"))
        if rh is not None:
            batch.rows.append((t, city.key, "humidity", round(float(rh), 4), "%"))
    # NWS can repeat an observation; keep one per (time, city, metric)
    batch.rows = list({(r[0], r[1], r[2]): r for r in batch.rows}.values())
    return batch


def noaa_ncei_temperature(start: date, until: date) -> Batch:
    """GHCN-Daily max/min temperature. Daily mean = (max + min) / 2, NOAA's own definition."""
    batch = Batch("noaa-ncei", f"NOAA NCEI GHCN-Daily TMAX/TMIN {start}..{until - timedelta(days=1)}",
                  "quality-assured", "snowflake")
    station_city = {c.ghcnd_station: c.key for c in CITIES.values()}
    body = batch.fetch("https://www.ncei.noaa.gov/access/services/data/v1", {
        "dataset": "daily-summaries", "stations": ",".join(station_city), "dataTypes": "TMAX,TMIN",
        "startDate": start.isoformat(), "endDate": (until - timedelta(days=1)).isoformat(),
        "format": "json", "units": "metric"})
    for r in json.loads(body):
        if r.get("TMAX") and r.get("TMIN"):
            hi, lo = float(r["TMAX"]), float(r["TMIN"])
            batch.rows.append((date.fromisoformat(r["DATE"]), station_city[r["STATION"]], "temperature", "°C",
                               round((hi + lo) / 2, 4), round(lo, 4), round(hi, 4), 1))
    return batch


def _relative_humidity(temp_c: float, dewpoint_c: float) -> float:
    # Magnus formula (Alduchov & Eskridge 1996 coefficients)
    return 100 * math.exp(17.625 * dewpoint_c / (243.04 + dewpoint_c)) / math.exp(17.625 * temp_c / (243.04 + temp_c))


def noaa_gsod_humidity(start: date, until: date) -> Batch:
    """Daily mean relative humidity, computed from NCEI Global Summary of the Day temperature and dew point."""
    batch = Batch("noaa-ncei", f"NOAA NCEI GSOD TEMP/DEWP -> relative humidity {start}..{until - timedelta(days=1)}",
                  "quality-assured", "snowflake")
    station_city = {c.gsod_station: c.key for c in CITIES.values()}
    body = batch.fetch("https://www.ncei.noaa.gov/access/services/data/v1", {
        "dataset": "global-summary-of-the-day", "stations": ",".join(station_city), "dataTypes": "TEMP,DEWP",
        "startDate": start.isoformat(), "endDate": (until - timedelta(days=1)).isoformat(), "format": "json"})
    for r in json.loads(body):
        try:
            t_f, d_f = float(r["TEMP"]), float(r["DEWP"])  # GSOD reports °F; 9999.9 = missing
        except (KeyError, ValueError):
            continue
        if t_f > 999 or d_f > 999:
            continue
        rh = min(100.0, _relative_humidity((t_f - 32) / 1.8, (d_f - 32) / 1.8))
        batch.rows.append((date.fromisoformat(r["DATE"]), station_city[r["STATION"]], "humidity", "%",
                           round(rh, 4), round(rh, 4), round(rh, 4), 1))
    return batch


def noaa_gml_co2(start: date, until: date, store: str) -> Batch:
    """Mauna Loa daily CO2 (global background). Recent daily values are preliminary."""
    batch = Batch("noaa-gml", f"NOAA GML Mauna Loa daily CO2 {start}..{until - timedelta(days=1)}",
                  "preliminary" if store == "tiger" else "quality-assured", store)
    body = batch.fetch("https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_daily_mlo.txt")
    for line in body.decode().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        y, m, d, _decimal, value = line.split()[:5]
        day, v = date(int(y), int(m), int(d)), float(value)
        if start <= day < until and v > 0:
            if store == "tiger":
                batch.rows.append((datetime(day.year, day.month, day.day, tzinfo=timezone.utc), GLOBAL, "co2", round(v, 4), "ppm"))
            else:
                batch.rows.append((day, GLOBAL, "co2", "ppm", round(v, 4), round(v, 4), round(v, 4), 1))
    return batch


# ---------------------------------------------------------------- USGS

USGS_PARAMS = {"00060": ("streamflow", "ft³/s"), "00010": ("water_temperature", "°C")}


def _usgs_series(body: bytes):
    site_city = {c.usgs_site: c.key for c in CITIES.values()}
    for ts in json.loads(body)["value"]["timeSeries"]:
        city = site_city.get(ts["sourceInfo"]["siteCode"][0]["value"])
        param = ts["variable"]["variableCode"][0]["value"]
        no_data = ts["variable"].get("noDataValue")
        if city and param in USGS_PARAMS:
            for block in ts["values"]:
                for v in block["value"]:
                    if v["value"] not in (None, "", str(no_data)) and float(v["value"]) != no_data:
                        yield city, *USGS_PARAMS[param], v["dateTime"], float(v["value"])


def usgs_recent(since: datetime) -> Batch:
    batch = Batch("usgs-nwis", f"USGS NWIS instantaneous values since {since:%Y-%m-%d %H:%M} UTC", "preliminary", "tiger")
    body = batch.fetch("https://waterservices.usgs.gov/nwis/iv/", {
        "format": "json", "sites": ",".join(c.usgs_site for c in CITIES.values()),
        "parameterCd": ",".join(USGS_PARAMS), "startDT": since.strftime("%Y-%m-%dT%H:%MZ")})
    for city, metric, unit, stamp, value in _usgs_series(body):
        batch.rows.append((datetime.fromisoformat(stamp).astimezone(timezone.utc), city, metric, round(value, 4), unit))
    return batch


def usgs_daily(start: date, until: date) -> Batch:
    batch = Batch("usgs-nwis", f"USGS NWIS daily means {start}..{until - timedelta(days=1)}", "quality-assured", "snowflake")
    body = batch.fetch("https://waterservices.usgs.gov/nwis/dv/", {
        "format": "json", "sites": ",".join(c.usgs_site for c in CITIES.values()),
        "parameterCd": ",".join(USGS_PARAMS), "statCd": "00003",
        "startDT": start.isoformat(), "endDT": (until - timedelta(days=1)).isoformat()})
    for city, metric, unit, stamp, value in _usgs_series(body):
        batch.rows.append((date.fromisoformat(stamp[:10]), city, metric, unit, round(value, 4), round(value, 4), round(value, 4), 1))
    return batch
