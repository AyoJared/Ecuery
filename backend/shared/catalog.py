"""What Ecuery measures, where, and which official station/monitor each number comes from.

Every city maps to the government monitors inside it; values are the mean across
those monitors. CO2 is the one global metric: agencies don't publish ambient CO2 per
city, so it comes from NOAA's Mauna Loa record and is reported as global.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Metric:
    code: str
    label: str
    unit: str
    hint: str  # how people ask about it (fed to Gemini)
    global_only: bool = False


@dataclass(frozen=True)
class City:
    key: str
    name: str
    counties: tuple[str, ...]      # 5-digit state+county FIPS: EPA monitors inside the city
    nws_station: str               # NOAA NWS live observations
    ghcnd_station: str             # NOAA NCEI daily temperature history
    gsod_station: str              # NOAA NCEI Global Summary of the Day (dew point -> humidity)
    usgs_site: str                 # USGS stream gauge
    notes: dict = field(default_factory=dict, compare=False, hash=False)


METRICS: dict[str, Metric] = {m.code: m for m in [
    Metric("pm25", "PM2.5", "µg/m³", "fine particulate matter PM2.5, smoke, haze, soot, 'air quality' / AQI in general"),
    Metric("o3", "Ozone", "ppb", "ozone, smog"),
    Metric("no2", "NO2", "ppb", "nitrogen dioxide, traffic / vehicle exhaust pollution"),
    Metric("co2", "CO2", "ppm", "carbon dioxide concentration, CO2 levels (global, Mauna Loa)", global_only=True),
    Metric("temperature", "Temperature", "°C", "air temperature, heat, cold, weather"),
    Metric("humidity", "Humidity", "%", "relative humidity, moisture, muggy"),
    Metric("streamflow", "Streamflow", "ft³/s", "river / stream flow, discharge, flooding, drought, water levels"),
    Metric("water_temperature", "Water temperature", "°C", "river / stream water temperature"),
]}

CITIES: dict[str, City] = {c.key: c for c in [
    City("philadelphia", "Philadelphia", ("42101",), "KPHL", "USW00013739", "72408013739", "01474500",
         {"usgs": "Schuylkill River at Philadelphia", "weather": "Philadelphia International Airport"}),
    City("new_york", "New York", ("36005", "36047", "36061", "36081", "36085"), "KNYC", "USW00094728", "72505394728",
         "01302020", {"usgs": "Bronx River at NY Botanical Garden", "weather": "Central Park"}),
    City("pittsburgh", "Pittsburgh", ("42003",), "KPIT", "USW00094823", "72520094823", "03086000",
         {"usgs": "Ohio River at Sewickley", "weather": "Pittsburgh International Airport"}),
    # Baltimore City has no real-time AirNow monitors; the surrounding Baltimore County ones (Essex, Padonia) count.
    City("baltimore", "Baltimore", ("24510", "24005"), "KBWI", "USW00093721", "72406093721", "01589352",
         {"usgs": "Gwynns Falls at Washington Blvd", "weather": "BWI Airport", "air": "Baltimore City + Baltimore County monitors"}),
]}

GLOBAL = "global"  # location key for global-only metrics

LOCATIONS = set(CITIES) | {GLOBAL}


def unit(metric: str) -> str:
    return METRICS[metric].unit if metric in METRICS else ""


def label(metric: str) -> str:
    return METRICS[metric].label if metric in METRICS else metric
