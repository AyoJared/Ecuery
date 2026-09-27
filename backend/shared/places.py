"""Any place on Earth -> a stable location key the databases use.

Resolution order:
  1. a measured city from shared/catalog.py (EPA/NOAA/USGS monitors), e.g. "philadelphia"
  2. a place already seen before (Tiger table `places`, plus remembered aliases)
  3. Open-Meteo geocoding (GeoNames), most populous match; the country narrows it when given

Measured cities are "measured"; everything else is served from global modeled data ("modeled").
"""

import math
import os
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass

import httpx
import psycopg
from psycopg.rows import dict_row

from .catalog import CITIES, GLOBAL

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Ecuery environmental data (OwlHacks 2026; jaredwerts2006@gmail.com)"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS places (
        key TEXT PRIMARY KEY, name TEXT NOT NULL, admin1 TEXT, country TEXT, country_code TEXT,
        lat DOUBLE PRECISION NOT NULL, lon DOUBLE PRECISION NOT NULL, timezone TEXT, population BIGINT,
        geonames_id BIGINT, kind TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "ALTER TABLE places ADD COLUMN IF NOT EXISTS feature_code TEXT",
    "ALTER TABLE places ADD COLUMN IF NOT EXISTS radius_km DOUBLE PRECISION",
    "ALTER TABLE places ADD COLUMN IF NOT EXISTS source_ref TEXT",
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
    feature_code: str | None = None  # city, town, county, state, province, country, ...
    radius_km: float | None = None   # how far the place extends (from its bounding box), for event searches

    @property
    def label(self) -> str:
        if self.kind == "global":
            return "Global"
        if self.feature_code in ("country", "continent") or self.name == self.country:
            return self.name
        if self.country_code == "US" and self.admin1:
            return f"{self.name}, {self.admin1}"
        return f"{self.name}, {self.country}" if self.country else self.name

    def to_dict(self) -> dict:
        return asdict(self) | {"label": self.label}


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


MEASURED_RADIUS_KM = {"philadelphia": 20, "new_york": 30, "pittsburgh": 12, "baltimore": 12}
STATES = {"philadelphia": "Pennsylvania", "pittsburgh": "Pennsylvania", "new_york": "New York", "baltimore": "Maryland"}


def _measured(city) -> Place:
    return Place(city.key, city.name, "United States", city.lat, city.lon, "measured", STATES.get(city.key), "US",
                 feature_code="city", radius_km=MEASURED_RADIUS_KM.get(city.key, 20))


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
                 r["country_code"], r["timezone"], r["population"], r.get("feature_code"), r.get("radius_km"))


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


# Radius (km) clamps per place type: bounding boxes can include remote islands (Tokyo's reaches ~1,200 km).
RADIUS_CLAMP = {"city": (5, 40), "town": (3, 25), "village": (2, 15), "municipality": (5, 40), "suburb": (2, 15),
                "county": (10, 120), "state": (50, 800), "province": (50, 800), "region": (50, 800),
                "country": (100, 1500), "continent": (1000, 3000)}


def _geocode_and_store(text: str, alias: str) -> Place:
    best = _nominatim(text) or _open_meteo(text)
    if not best:
        raise PlaceNotFound(f"couldn't find a place called '{text}'")
    with _conn() as conn:
        existing = conn.execute("SELECT * FROM places WHERE source_ref = %s", (best["ref"],)).fetchone()
        if existing:
            place = _from_row(existing)
        else:
            cc = (best.get("country_code") or "xx").lower()
            key = f"{slug(best['name'])}_{cc}"
            if conn.execute("SELECT 1 FROM places WHERE key = %s", (key,)).fetchone() or key in CITIES:
                key = f"{slug(best['name'])}_{slug(best.get('admin1') or best['feature_code'] or 'x')}_{cc}"
            place = Place(key, best["name"], best.get("country", ""), best["lat"], best["lon"], "modeled",
                          best.get("admin1"), (best.get("country_code") or "").upper() or None, best.get("timezone"),
                          best.get("population"), best["feature_code"], best.get("radius_km"))
            conn.execute("""INSERT INTO places (key, name, admin1, country, country_code, lat, lon, timezone,
                               population, kind, feature_code, radius_km, source_ref)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (key) DO NOTHING""",
                         (place.key, place.name, place.admin1, place.country, place.country_code, place.lat, place.lon,
                          place.timezone, place.population, place.kind, place.feature_code, place.radius_km, best["ref"]))
        conn.execute("INSERT INTO place_aliases (alias, key) VALUES (%s, %s) ON CONFLICT (alias) DO NOTHING",
                     (alias, place.key))
    return place


_last_nominatim = 0.0


def _nominatim(text: str) -> dict | None:
    """OpenStreetMap geocoder: knows cities, counties, states, countries, and gives each one's real extent."""
    global _last_nominatim
    wait = 1.1 - (time.monotonic() - _last_nominatim)  # usage policy: max 1 request per second
    if wait > 0:
        time.sleep(wait)
    _last_nominatim = time.monotonic()
    try:
        resp = _http.get(NOMINATIM_URL, params={"q": text, "format": "jsonv2", "limit": 5, "addressdetails": 1,
                                                "accept-language": "en"})
        resp.raise_for_status()
        results = [r for r in resp.json() if r.get("addresstype") in RADIUS_CLAMP or r.get("category") in ("place", "boundary")]
    except (httpx.HTTPError, ValueError):
        return None
    if not results:
        return None
    r = results[0]  # Nominatim ranks by importance
    kind = r.get("addresstype") if r.get("addresstype") in RADIUS_CLAMP else "city"
    s_, n_, w_, e_ = map(float, r["boundingbox"])
    half_diag = 6371 * math.acos(min(1, max(-1, math.sin(math.radians(s_)) * math.sin(math.radians(n_)) +
                                             math.cos(math.radians(s_)) * math.cos(math.radians(n_)) *
                                             math.cos(math.radians(e_ - w_))))) / 2
    lo, hi = RADIUS_CLAMP[kind]
    address = r.get("address", {})
    return {"ref": f"osm:{r['osm_type']}:{r['osm_id']}", "name": r.get("name") or text.split(",")[0].strip(),
            "lat": float(r["lat"]), "lon": float(r["lon"]), "feature_code": kind,
            "admin1": address.get("state") if kind not in ("state", "province", "region", "country") else None,
            "country": address.get("country", ""), "country_code": address.get("country_code"),
            "radius_km": round(min(hi, max(lo, half_diag)), 1)}


def _open_meteo(text: str) -> dict | None:
    """Fallback geocoder (GeoNames populated places and countries)."""
    name, _, qualifier = text.partition(",")
    candidates = _search(name.strip())
    if not candidates and " " in name.strip():  # "Lagos Nigeria" -> "Lagos" + qualifier "Nigeria"
        first, _, rest = name.strip().rpartition(" ")
        candidates, qualifier = _search(first), rest
    if not candidates:
        return None
    q = slug(qualifier)
    if q:
        narrowed = [c for c in candidates if q in (slug(c.get("country", "")), slug(c.get("country_code", "")),
                                                    slug(c.get("admin1", "")))]
        candidates = narrowed or candidates
    best = max(candidates, key=lambda c: c.get("population") or 0)
    return {"ref": f"geonames:{best['id']}", "name": best["name"], "lat": best["latitude"], "lon": best["longitude"],
            "feature_code": "country" if best.get("feature_code") == "PCLI" else "city", "admin1": best.get("admin1"),
            "country": best.get("country", ""), "country_code": best.get("country_code"),
            "timezone": best.get("timezone"), "population": best.get("population")}


def _search(name: str) -> list[dict]:
    resp = _http.get(GEOCODE_URL, params={"name": name, "count": 10, "language": "en", "format": "json"})
    resp.raise_for_status()
    return resp.json().get("results", [])


def display_name(key: str) -> str:
    place = get(key)
    return place.label if place else key.replace("_", " ").title()
