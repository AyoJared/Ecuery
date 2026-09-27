"""Any place on Earth -> a stable location key the databases use.

Resolution order:
  1. a measured city from shared/catalog.py (EPA/NOAA/USGS monitors), e.g. "philadelphia"
  2. a place already seen before (Tiger table `places`, plus remembered aliases)
  3. Open-Meteo geocoding (GeoNames), most populous match; the country narrows it when given

Measured cities are "measured"; everything else is served from global modeled data ("modeled").
"""

import os
import re
import threading
import unicodedata
from dataclasses import asdict, dataclass

import httpx
import psycopg
from psycopg.rows import dict_row

from .catalog import CITIES, GLOBAL

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = "Ecuery environmental data (OwlHacks 2026)"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS places (
        key TEXT PRIMARY KEY, name TEXT NOT NULL, admin1 TEXT, country TEXT, country_code TEXT,
        lat DOUBLE PRECISION NOT NULL, lon DOUBLE PRECISION NOT NULL, timezone TEXT, population BIGINT,
        geonames_id BIGINT, kind TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE TABLE IF NOT EXISTS place_aliases (alias TEXT PRIMARY KEY, key TEXT NOT NULL REFERENCES places(key))",
]


class PlaceNotFound(LookupError):
    pass


@dataclass
class Place:
    key: str
    name: str
    country: str
    lat: float
    lon: float
    kind: str  # "measured" | "modeled" | "global"
    admin1: str | None = None
    country_code: str | None = None
    timezone: str | None = None
    population: int | None = None

    @property
    def label(self) -> str:
        if self.kind == "global":
            return "Global"
        if self.country_code == "US" and self.admin1:
            return f"{self.name}, {self.admin1}"
        return f"{self.name}, {self.country}" if self.country else self.name

    def to_dict(self) -> dict:
        return asdict(self) | {"label": self.label}


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


STATES = {"philadelphia": "Pennsylvania", "pittsburgh": "Pennsylvania", "new_york": "New York", "baltimore": "Maryland"}


def _measured(city) -> Place:
    return Place(city.key, city.name, "United States", city.lat, city.lon, "measured", STATES.get(city.key), "US")


GLOBAL_PLACE = Place(GLOBAL, "Global", "", 19.536, -155.576, "global")  # Mauna Loa Observatory
_ready = False
_lock = threading.Lock()
_http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)


def _conn():
    return psycopg.connect(os.environ["TIGER_DATABASE_URL"], connect_timeout=15, row_factory=dict_row)


def _ensure_tables() -> None:
    global _ready
    if not _ready:
        with _conn() as conn:
            for sql in SCHEMA:
                conn.execute(sql)
        _ready = True


def _from_row(r: dict) -> Place:
    return Place(r["key"], r["name"], r["country"] or "", r["lat"], r["lon"], r["kind"], r["admin1"],
                 r["country_code"], r["timezone"], r["population"])


def get(key: str) -> Place | None:
    if key == GLOBAL:
        return GLOBAL_PLACE
    if key in CITIES:
        return _measured(CITIES[key])
    _ensure_tables()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM places WHERE key = %s", (key,)).fetchone()
    return _from_row(row) if row else None


NICKNAMES = {"nyc": "new_york", "new_york_city": "new_york", "philly": "philadelphia", "bmore": "baltimore"}
US_SUFFIXES = ("united_states", "usa", "us", "pennsylvania", "pa", "new_york", "ny", "maryland", "md")


def _measured_match(text: str) -> Place | None:
    s = slug(text)
    for _ in range(2):  # "Philadelphia, PA, USA" -> "philadelphia"
        for suffix in US_SUFFIXES:
            if s.endswith("_" + suffix) and s != suffix:
                s = s[: -len(suffix) - 1]
                break
    s = NICKNAMES.get(s, s)
    return _measured(CITIES[s]) if s in CITIES else None


def resolve(text: str) -> Place:
    """Place name as a person would say it ("Delhi", "Paris, France", "new_york", "Lagos Nigeria") -> Place."""
    text = text.strip()
    if not text:
        raise PlaceNotFound("empty place name")
    if slug(text) == GLOBAL:
        return GLOBAL_PLACE
    if (m := _measured_match(text)) is not None:
        return m
    if (known := get(slug(text))) is not None:  # already a location key
        return known
    alias = slug(text)
    _ensure_tables()
    with _conn() as conn:
        row = conn.execute("SELECT p.* FROM place_aliases a JOIN places p ON p.key = a.key WHERE a.alias = %s",
                           (alias,)).fetchone()
    if row:
        return _from_row(row)

    with _lock:  # one geocode + insert at a time
        return _geocode_and_store(text, alias)


def _geocode_and_store(text: str, alias: str) -> Place:
    name, _, qualifier = text.partition(",")
    candidates = _search(name.strip())
    if not candidates and " " in name.strip():  # "Lagos Nigeria" -> "Lagos" + qualifier "Nigeria"
        first, _, rest = name.strip().rpartition(" ")
        candidates, qualifier = _search(first), rest
    if not candidates:
        raise PlaceNotFound(f"couldn't find a place called '{text}'")
    q = slug(qualifier)
    if q:
        narrowed = [c for c in candidates if q in (slug(c.get("country", "")), slug(c.get("country_code", "")),
                                                    slug(c.get("admin1", "")))]
        candidates = narrowed or candidates
    best = max(candidates, key=lambda c: c.get("population") or 0)

    base = slug(best["name"]) + "_" + (best.get("country_code") or "xx").lower()
    with _conn() as conn:
        existing = conn.execute("SELECT * FROM places WHERE geonames_id = %s", (best["id"],)).fetchone()
        if existing:
            place = _from_row(existing)
        else:
            key = base
            clash = conn.execute("SELECT 1 FROM places WHERE key = %s", (key,)).fetchone()
            if clash or key in CITIES:
                key = f"{slug(best['name'])}_{slug(best.get('admin1') or 'x')}_{(best.get('country_code') or 'xx').lower()}"
            place = Place(key, best["name"], best.get("country", ""), best["latitude"], best["longitude"], "modeled",
                          best.get("admin1"), best.get("country_code"), best.get("timezone"), best.get("population"))
            conn.execute("""INSERT INTO places (key, name, admin1, country, country_code, lat, lon, timezone,
                               population, geonames_id, kind) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (key) DO NOTHING""",
                         (place.key, place.name, place.admin1, place.country, place.country_code, place.lat,
                          place.lon, place.timezone, place.population, best["id"], place.kind))
        conn.execute("INSERT INTO place_aliases (alias, key) VALUES (%s, %s) ON CONFLICT (alias) DO NOTHING",
                     (alias, place.key))
    return place


def _search(name: str) -> list[dict]:
    resp = _http.get(GEOCODE_URL, params={"name": name, "count": 10, "language": "en", "format": "json"})
    resp.raise_for_status()
    return resp.json().get("results", [])


def display_name(key: str) -> str:
    place = get(key)
    return place.label if place else key.replace("_", " ").title()
