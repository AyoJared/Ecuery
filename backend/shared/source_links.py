"""Links people can open to review where an answer's data came from.

Every answered card gets `source_links`: one entry per data source, pointing at the agency's
public page for that dataset (`url`) and, when we have it, the exact request Ecuery made
(`data_url`, with credentials stripped). Built from what the card already records -- ingest
batches (provenance), event sources, forecast-model calls and cited web pages -- and, only when
none of those exist (e.g. answers served from sample data), the usual source for each metric.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Batch / source key -> (name people recognise, public page describing the dataset)
SOURCES: dict[str, tuple[str, str]] = {
    "epa-aqs": ("EPA Air Quality System", "https://www.epa.gov/aqs"),
    "epa-airnow": ("EPA AirNow", "https://www.airnow.gov/"),
    "noaa-nws": ("NOAA National Weather Service observations", "https://www.weather.gov/documentation/services-web-api"),
    "noaa-ncei": ("NOAA NCEI station climate data", "https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily"),
    "noaa-gml": ("NOAA Global Monitoring Lab, Mauna Loa CO₂", "https://gml.noaa.gov/ccgg/trends/"),
    "usgs-nwis": ("USGS National Water Information System", "https://waterdata.usgs.gov/nwis"),
    "copernicus-cams": ("Copernicus Atmosphere Monitoring Service", "https://atmosphere.copernicus.eu/"),
    "cams": ("Copernicus CAMS air-quality forecast", "https://atmosphere.copernicus.eu/charts/packages/cams/"),
    "ecmwf-era5": ("ECMWF ERA5 reanalysis (Copernicus)", "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels"),
    "ecmwf-ensemble": ("ECMWF ensemble forecast", "https://www.ecmwf.int/en/forecasts/documentation-and-support/medium-range-forecasts"),
    "gfs-ensemble": ("NOAA GFS ensemble forecast", "https://www.ncei.noaa.gov/products/weather-climate-models/global-ensemble-forecast"),
    "open-meteo-forecast": ("Open-Meteo weather models", "https://open-meteo.com/"),
    "glofas": ("GloFAS river discharge (Copernicus)", "https://www.globalfloods.eu/"),
    "noaa-storm-events": ("NOAA NCEI Storm Events Database", "https://www.ncdc.noaa.gov/stormevents/"),
    "usgs-earthquakes": ("USGS earthquake catalog", "https://earthquake.usgs.gov/earthquakes/search/"),
    "noaa-sig-earthquakes": ("NOAA NCEI Significant Earthquake Database", "https://www.ngdc.noaa.gov/hazel/view/hazards/earthquake/search"),
    "gdacs": ("GDACS disaster alerts", "https://www.gdacs.org/"),
    "ibtracs": ("NOAA IBTrACS tropical cyclone tracks", "https://www.ncei.noaa.gov/products/international-best-track-archive"),
    "nasa-eonet": ("NASA EONET natural events", "https://eonet.gsfc.nasa.gov/"),
    "noaa-globaltemp": ("NOAA GlobalTemp", "https://www.ncei.noaa.gov/products/land-based-station/noaa-global-temp"),
    "nsidc-seaice": ("NSIDC Sea Ice Index", "https://nsidc.org/data/g02135"),
    "noaa-star": ("NOAA STAR satellite sea level", "https://www.star.nesdis.noaa.gov/socd/lsa/SeaLevelRise/"),
    "gwis-owid": ("Copernicus GWIS burned area (via Our World in Data)", "https://ourworldindata.org/wildfires"),
}

# Where each metric usually comes from; used only when an answer records no sources of its own.
METRIC_SOURCES: dict[str, list[str]] = {
    "pm25": ["epa-aqs", "copernicus-cams"], "o3": ["epa-aqs", "copernicus-cams"], "no2": ["epa-aqs", "copernicus-cams"],
    "co2": ["noaa-gml"], "temperature": ["noaa-ncei", "ecmwf-era5"], "humidity": ["noaa-ncei"],
    "streamflow": ["usgs-nwis"], "water_temperature": ["usgs-nwis"], "precipitation": ["ecmwf-era5"],
    "dust": ["copernicus-cams"], "burned_area": ["gwis-owid"], "global_temperature": ["noaa-globaltemp"],
    "arctic_sea_ice": ["nsidc-seaice"], "antarctic_sea_ice": ["nsidc-seaice"], "sea_level": ["noaa-star"],
}

# Query parameters that can carry credentials; never shown to users.
SECRET_PARAMS = {"key", "api_key", "apikey", "token", "access_token", "email", "password", "secret", "client_secret"}


def public_url(url: str | None) -> str | None:
    """The URL with credential-looking query parameters removed (None for anything that isn't http/https)."""
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in SECRET_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def source_links(card: dict) -> list[dict]:
    links: dict[str, dict] = {}  # keyed by source (or URL for web pages), first seen wins

    def add(key: str, detail: str | None = None, data_url: str | None = None, usual: bool = False):
        name, url = SOURCES.get(key, (key, None))
        entry = links.setdefault(key, {"name": name, "url": url, "detail": detail, "data_url": None, "usual": usual})
        entry["data_url"] = entry["data_url"] or public_url(data_url)
        entry["detail"] = entry["detail"] or detail

    provenance = card.get("provenance") or []
    request_urls = _request_urls([p["batch_id"] for p in provenance if p.get("batch_id") and not p.get("request_url")])
    for p in provenance:
        add(p.get("source", ""), p.get("dataset"), p.get("request_url") or request_urls.get(p.get("batch_id")))
    for key in (card.get("plan") or {}).get("sources") or []:
        if key != "none":
            add(key)
    for f in card.get("forecast_sources") or []:
        add(f.get("source", ""), f.get("dataset"), f.get("url"))
    for s in (card.get("web") or {}).get("sources") or []:
        url = public_url(s.get("url"))
        if url:
            links.setdefault(url, {"name": s.get("title") or s.get("site") or url, "url": url,
                                   "detail": s.get("site"), "data_url": None, "usual": False})

    if not links:
        for d in card.get("data") or []:
            for key in METRIC_SOURCES.get(d.get("metric", ""), []):
                add(key, usual=True)

    # Drop anything we can't link to (an unknown source key with no URL at all).
    return [l for l in links.values() if l["url"] or l["data_url"]]


def _request_urls(batch_ids: list[str]) -> dict[str, str]:
    """First recorded request per batch, for cards cached before provenance carried request_url."""
    if not batch_ids:
        return {}
    try:
        from ingest import store
        rows = store.registry(sorted(set(batch_ids)))
    except Exception:  # links are a nicety; never block an answer on the registry
        return {}
    out = {}
    for r in rows:
        url = next((q["url"] for q in (r.get("manifest") or {}).get("requests", []) if q.get("url")), None)
        if url:
            out[r["batch_id"]] = url
    return out


def with_source_links(response: dict) -> dict:
    """Attach `source_links` to an answered /ask response (other statuses pass through unchanged)."""
    if response.get("status") == "answered":
        response["source_links"] = source_links(response)
    return response
