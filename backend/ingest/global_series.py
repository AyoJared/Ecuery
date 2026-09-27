"""Long global climate records and country-level burned area (no API keys).

  noaa-globaltemp   Global land+ocean temperature anomaly vs 1901-2000, monthly, 1850 ->
  noaa-gml          Mauna Loa CO2, monthly 1958-2018 (daily from 2019 is loaded by ingest.sources)
  nsidc-seaice      Arctic and Antarctic sea ice extent, daily (every other day before 1988), 1978 ->
  noaa-star         Global mean sea level from satellite altimetry, ~10-day, 1993 ->
  gwis-owid         Annual area burned by wildfires per country / region, 2012 ->
                    (Copernicus GWIS, as published by Our World in Data)

History goes to Snowflake; the last RECENT_DAYS of the daily sea-ice record also goes to Tiger.
"""

import csv
import io
from datetime import date, datetime, timedelta, timezone

from shared.catalog import GLOBAL
from shared.places import slug

from .provenance import Batch

GLOBALTEMP_URL = ("https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/time-series/"
                  "globe/tavg/land_ocean/1/0/1850-{year}/data.csv")
CO2_MONTHLY_URL = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv"
SEAICE_URL = "https://noaadata.apps.nsidc.org/NOAA/G02135/{hemi}/daily/data/{prefix}_seaice_extent_daily_v4.0.csv"
SEALEVEL_URL = "https://www.star.nesdis.noaa.gov/socd/lsa/SeaLevelRise/slr/slr_sla_gbl_keep_ref_90.csv"
BURNED_URL = "https://ourworldindata.org/grapher/annual-area-burnt-by-wildfires.csv"


def _row(day: date, metric: str, unit: str, value: float, location: str = GLOBAL, samples: int = 1) -> tuple:
    v = round(float(value), 4)
    return (day, location, metric, unit, v, v, v, samples)


def global_temperature(until: date) -> Batch:
    batch = Batch("noaa-globaltemp", "NOAA GlobalTemp land+ocean anomaly vs 1901-2000, monthly 1850 ->",
                  "quality-assured", "snowflake")
    body = batch.fetch(GLOBALTEMP_URL.format(year=until.year)).decode()
    for line in body.splitlines():
        if not line or line.startswith("#") or not line[0].isdigit():
            continue
        stamp, value = line.split(",")[:2]
        day = date(int(stamp[:4]), int(stamp[4:6]), 1)
        if day < until and value.strip() not in ("", "-999", "-9999"):
            batch.rows.append(_row(day, "global_temperature", "°C", value))
    return batch


def co2_monthly(until: date) -> Batch:
    """1958-2018 monthly means; daily values from 2019 come from ingest.sources.noaa_gml_co2."""
    batch = Batch("noaa-gml", "NOAA GML Mauna Loa CO2 monthly means 1958-2018", "quality-assured", "snowflake")
    body = batch.fetch(CO2_MONTHLY_URL).decode()
    for line in body.splitlines():
        if not line or line.startswith("#") or not line[0].isdigit():
            continue
        f = line.split(",")
        year, month, value = int(f[0]), int(f[1]), float(f[3])
        day = date(year, month, 1)
        if year < 2019 and day < until and value > 0:
            batch.rows.append(_row(day, "co2", "ppm", value))
    return batch


def sea_ice(until: date, recent_since: datetime | None = None) -> list[Batch]:
    """Arctic + Antarctic extent. Returns [history batch] (+ [recent batch] for Tiger when recent_since is given)."""
    history = Batch("nsidc-seaice", "NSIDC Sea Ice Index v4 daily extent, Arctic and Antarctic, 1978 ->",
                    "quality-assured", "snowflake")
    recent = Batch("nsidc-seaice", "NSIDC Sea Ice Index v4 daily extent, recent days", "preliminary", "tiger")
    for hemi, prefix, metric in (("north", "N", "arctic_sea_ice"), ("south", "S", "antarctic_sea_ice")):
        body = history.fetch(SEAICE_URL.format(hemi=hemi, prefix=prefix)).decode()
        if recent_since:
            recent.requests.append(history.requests[-1])  # same file, same fingerprint
        for rec in csv.reader(io.StringIO(body)):
            try:
                day = date(int(rec[0]), int(rec[1]), int(rec[2]))
                extent = float(rec[3])
            except (ValueError, IndexError):
                continue  # header lines
            if extent <= 0:
                continue
            if day < until:
                history.rows.append(_row(day, metric, "million km²", extent))
            elif recent_since and datetime(day.year, day.month, day.day, tzinfo=timezone.utc) >= recent_since:
                recent.rows.append((datetime(day.year, day.month, day.day, tzinfo=timezone.utc), GLOBAL, metric,
                                    round(extent, 4), "million km²"))
    return [history] + ([recent] if recent_since else [])


def sea_level(until: date) -> Batch:
    batch = Batch("noaa-star", "NOAA STAR global mean sea level (TOPEX/Jason/Sentinel-6), annual signal kept, 1993 ->",
                  "quality-assured", "snowflake")
    body = batch.fetch(SEALEVEL_URL).decode()
    by_day: dict[date, list[float]] = {}
    for line in body.splitlines():
        if not line or line.startswith("#") or not line[0].isdigit():
            continue
        f = line.split(",")
        values = [float(x) for x in f[1:] if x.strip()]
        if not values:
            continue
        t = float(f[0])
        day = date(int(t), 1, 1) + timedelta(days=int((t - int(t)) * 365.25))
        if day < until:
            by_day.setdefault(day, []).append(values[-1])  # newest mission when two overlap
    for day, vals in sorted(by_day.items()):
        batch.rows.append(_row(day, "sea_level", "mm", sum(vals) / len(vals), samples=len(vals)))
    return batch


def burned_area(until: date) -> Batch:
    batch = Batch("gwis-owid", "Copernicus GWIS annual burned area per country/region (via Our World in Data), 2012 ->",
                  "quality-assured", "snowflake")
    body = batch.fetch(BURNED_URL, {"v": 1, "csvType": "full", "useColumnShortNames": "true"}).decode()
    for r in csv.DictReader(io.StringIO(body)):
        try:
            year, area = int(r["year"]), float(r["area_ha"])
        except (KeyError, ValueError):
            continue
        if date(year, 1, 1) < until:
            batch.rows.append(_row(date(year, 1, 1), "burned_area", "ha", area, location=burned_area_key(r["entity"])))
    return batch


def burned_area_key(entity_or_place_name: str) -> str:
    """Countries/regions are stored by name ('canada', 'united_states', 'world') so any geocoded place can find them."""
    return "area:" + slug(entity_or_place_name)
