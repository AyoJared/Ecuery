"""Forecast mode: what's coming, using the best honest method for each metric and horizon.

  Horizon        Temperature / humidity         Air quality (PM2.5, O3, NO2)  River flow        CO2
  <= 15 days     ECMWF 51-member ensemble        Copernicus CAMS (<= 4 days)   GloFAS (<= 30 d)  trend fit
  <= 35 days     NOAA GFS 31-member ensemble     typical conditions            typical           trend fit
  later          typical conditions (history)    typical conditions            typical           trend fit
  next year +    CMIP6 climate models, adjusted  typical conditions            typical           trend fit
                 to local history (temperature)

"Typical conditions" is NOT a forecast: it's the range seen on the same calendar dates in past years,
and every answer says which method produced which days. Bands are the 10th-90th percentile of the
ensemble / past years / climate models, or an 80% prediction interval for the CO2 fit.
"""

import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx

from shared import places
from shared.catalog import CITIES, GLOBAL, METRICS, label as metric_label, unit as metric_unit
from shared.series import DataUnavailable

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
CLIMATE_URL = "https://climate-api.open-meteo.com/v1/climate"
CMIP6_MODELS = ["CMCC_CM2_VHR4", "FGOALS_f3_H", "HiRAM_SIT_HR", "MRI_AGCM3_2_S", "EC_Earth3P_HR", "MPI_ESM1_2_XR", "NICAM16_8S"]
HISTORY_START = date(2019, 1, 1)
MAX_YEAR = 2050
AIR_SCALE = {"pm2_5": 1.0, "ozone": 24.45 / 48.00, "nitrogen_dioxide": 24.45 / 46.01}  # µg/m³ -> ppb
AIR_VAR = {"pm25": "pm2_5", "o3": "ozone", "no2": "nitrogen_dioxide"}
FT3 = 35.3147

METHOD_LABEL = {
    "ecmwf_ensemble": "ECMWF ensemble forecast (51 runs)",
    "gfs_ensemble": "NOAA GFS ensemble forecast (31 runs)",
    "cams": "Copernicus CAMS air-quality forecast",
    "glofas": "GloFAS river-flow forecast",
    "climatology": "Typical conditions for these dates in past years (not a forecast)",
    "climate_projection": "CMIP6 climate-model projection, adjusted to local history",
    "trend": "Trend and seasonal cycle fitted to the historical record",
}

_http = httpx.Client(headers={"User-Agent": "Ecuery environmental data (OwlHacks 2026)"}, timeout=90)


class NeedsClarification(Exception):
    pass


@dataclass
class ForecastPlan:
    pairs: list[tuple[str, str]]
    start: datetime             # first forecast day (inclusive)
    end: datetime               # exclusive
    places: dict = field(default_factory=dict)

    @property
    def metrics(self) -> list[str]:
        return list(dict.fromkeys(m for m, _ in self.pairs))

    @property
    def locations(self) -> list[str]:
        return list(dict.fromkeys(l for _, l in self.pairs))

    def to_dict(self) -> dict:
        return {"metrics": self.metrics, "locations": self.locations, "start": self.start.isoformat(),
                "end": self.end.isoformat(), "operation": "forecast",
                "places": {k: {x: v[x] for x in ("label", "kind", "lat", "lon")} for k, v in self.places.items()}}


def wants_forecast(parsed, today: date) -> bool:
    if parsed.operation == "forecast":
        return True
    try:
        return bool(parsed.start_date) and date.fromisoformat(parsed.start_date) > today
    except ValueError:
        return False


def make_forecast_plan(q, now: datetime, max_series: int = 4) -> ForecastPlan:
    today = now.date()
    if not q.metrics:
        raise NeedsClarification(q.clarification_question or "What should I forecast? For example temperature, "
                                 "PM2.5 or river flow.")
    city_metrics = [m for m in dict.fromkeys(q.metrics) if not METRICS[m].global_only]
    global_metrics = [m for m in dict.fromkeys(q.metrics) if METRICS[m].global_only]
    names = [l for l in dict.fromkeys(q.locations) if places.slug(l) != GLOBAL]
    if city_metrics and not names:
        raise NeedsClarification(q.clarification_question or "Which place should I forecast?")
    resolved = []
    for name in names:
        try:
            resolved.append(places.resolve(name))
        except places.PlaceNotFound:
            raise NeedsClarification(f"I couldn't find '{name}'. Could you add the country or state?")

    try:
        start_day = date.fromisoformat(q.start_date) if q.start_date else today + timedelta(days=1)
        end_day = date.fromisoformat(q.end_date) if q.end_date else start_day + timedelta(days=6)
    except ValueError:
        raise NeedsClarification("I couldn't work out when you mean. Try 'next week', 'this weekend' or 'in 2040'.")
    start_day = max(start_day, today)
    if end_day < start_day:
        raise NeedsClarification("That period has already passed. Did you mean a past period instead of a forecast?")
    if end_day.year > MAX_YEAR:
        raise NeedsClarification(f"I can only look ahead to {MAX_YEAR} (the end of the climate-model projections).")

    pairs = [(m, p.key) for m in city_metrics for p in resolved] + [(m, GLOBAL) for m in global_metrics]
    known = {p.key: p.to_dict() for p in resolved} | ({GLOBAL: places.GLOBAL_PLACE.to_dict()} if global_metrics else {})
    as_dt = lambda d: datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return ForecastPlan(pairs[:max_series], as_dt(start_day), as_dt(end_day + timedelta(days=1)), known)


# ---------------------------------------------------------------- helpers

class SourceLog:
    """Fingerprints of every forecast/model response used (committed to by the answer's Solana record)."""

    def __init__(self):
        self.entries: list[dict] = []

    def get(self, url: str, params: dict, source: str, dataset: str) -> dict:
        resp = _http.get(url, params=params)
        resp.raise_for_status()
        self.entries.append({"source": source, "dataset": dataset, "url": str(resp.url),
                             "sha256": hashlib.sha256(resp.content).hexdigest(), "bytes": len(resp.content),
                             "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "quality": "forecast"})
        return resp.json()


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _point(day: date, value: float, lo: float | None, hi: float | None, method: str, **extra) -> dict:
    r = lambda v: None if v is None else round(v, 2)
    return {"time": datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat(), "value": r(value),
            "lo": r(lo), "hi": r(hi), "method": method, "forecast": True, **extra}


def _days(start: date, end_exclusive: date):
    d = start
    while d < end_exclusive:
        yield d
        d += timedelta(days=1)


def _place(key: str) -> places.Place:
    p = places.get(key)
    if p is None:
        raise DataUnavailable(f"unknown place {key}")
    return p


# ---------------------------------------------------------------- model forecasts

def ensemble(place, metric: str, days: list[date], model: str, log: SourceLog) -> list[dict]:
    var = {"temperature": "temperature_2m_mean", "humidity": "relative_humidity_2m_mean",
           "precipitation": "precipitation_sum"}[metric]
    horizon = 15 if model == "ecmwf_ifs025" else 35
    data = log.get(ENSEMBLE_URL, {"latitude": place.lat, "longitude": place.lon, "daily": var, "models": model,
                                  "forecast_days": horizon, "timezone": "UTC"},
                   "ecmwf-ensemble" if model == "ecmwf_ifs025" else "gfs-ensemble",
                   f"{'ECMWF IFS' if model == 'ecmwf_ifs025' else 'NOAA GFS'} ensemble {metric} for {place.label}")["daily"]
    members = [k for k in data if k.startswith(var)]
    method = "ecmwf_ensemble" if model == "ecmwf_ifs025" else "gfs_ensemble"
    wanted = set(days)
    out = []
    for i, stamp in enumerate(data["time"]):
        day = date.fromisoformat(stamp)
        vals = [data[m][i] for m in members if data[m][i] is not None]
        if day in wanted and vals:
            out.append(_point(day, statistics.median(vals), _pct(vals, 0.1), _pct(vals, 0.9), method, members=len(vals)))
    return out


def cams(place, metric: str, days: list[date], log: SourceLog) -> list[dict]:
    var = AIR_VAR[metric]
    data = log.get(AIR_URL, {"latitude": place.lat, "longitude": place.lon, "hourly": var, "forecast_days": 5,
                             "timezone": "UTC"}, "copernicus-cams", f"Copernicus CAMS {metric} forecast for {place.label}")["hourly"]
    by_day: dict[date, list[float]] = defaultdict(list)
    for stamp, v in zip(data["time"], data[var]):
        if v is not None:
            by_day[date.fromisoformat(stamp[:10])].append(v * AIR_SCALE[var])
    # Deterministic model: no uncertainty band; the day's hourly range is reported separately.
    return [_point(d, statistics.fmean(by_day[d]), None, None, "cams", day_min=round(min(by_day[d]), 2),
                   day_max=round(max(by_day[d]), 2)) for d in days if len(by_day.get(d, [])) >= 12]


def glofas(place, days: list[date], log: SourceLog) -> list[dict]:
    from ingest.global_sources import river_cell
    lat, lon = river_cell(place)
    data = log.get(FLOOD_URL, {"latitude": lat, "longitude": lon, "forecast_days": 30,
                               "daily": "river_discharge,river_discharge_p25,river_discharge_p75"},
                   "glofas", f"GloFAS river discharge forecast near {place.label}")["daily"]
    wanted, out = set(days), []
    for i, stamp in enumerate(data["time"]):
        day = date.fromisoformat(stamp)
        v, lo, hi = data["river_discharge"][i], data["river_discharge_p25"][i], data["river_discharge_p75"][i]
        if day in wanted and v is not None:
            out.append(_point(day, v * FT3, lo and lo * FT3, hi and hi * FT3, "glofas"))
    return out


# ---------------------------------------------------------------- statistical methods

def _history(metric: str, location: str, today: date, since: date | None = None) -> list[tuple[date, float]]:
    """Daily history from Snowflake (2019 -> recent cutoff)."""
    from warehouse.repo import get_repo as get_warehouse
    since = since or HISTORY_START
    start = datetime(since.year, 1, 1, tzinfo=timezone.utc)
    end = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    result = get_warehouse().history(metric, location, start, end, "daily")
    return [(date.fromisoformat(p["time"][:10]), p["avg"]) for p in result["points"]], result.get("batches", [])


def climatology(history: list[tuple[date, float]], days: list[date], granularity: str) -> list[dict]:
    if not history:
        return []
    years = sorted({d.year for d, _ in history})
    if granularity == "daily":
        by_doy: dict[int, list[float]] = defaultdict(list)
        for d, v in history:
            by_doy[d.timetuple().tm_yday].append(v)
        out = []
        for day in days:
            doy = day.timetuple().tm_yday
            vals = [v for k in range(doy - 3, doy + 4) for v in by_doy.get((k - 1) % 366 + 1, [])]  # ±3-day window
            if len(vals) >= 5:
                out.append(_point(day, statistics.median(vals), _pct(vals, 0.1), _pct(vals, 0.9), "climatology",
                                  years=f"{years[0]}–{years[-1]}"))
        return out
    by_month: dict[int, list[float]] = defaultdict(list)
    for d, v in history:
        by_month[d.month].append(v)
    months = sorted({(d.year, d.month) for d in days})
    return [_point(date(y, m, 1), statistics.median(by_month[m]), _pct(by_month[m], 0.1), _pct(by_month[m], 0.9),
                   "climatology", years=f"{years[0]}–{years[-1]}") for y, m in months if len(by_month[m]) >= 10]


def trend_fit(history: list[tuple[date, float]], days: list[date], granularity: str) -> list[dict]:
    """OLS: level + linear trend + annual & semiannual harmonics; 80% prediction intervals."""
    import numpy as np
    t0 = HISTORY_START.toordinal()
    def features(d: date):
        t = (d.toordinal() - t0) / 365.25
        return [1.0, t, math.sin(2 * math.pi * t), math.cos(2 * math.pi * t), math.sin(4 * math.pi * t), math.cos(4 * math.pi * t)]
    X = np.array([features(d) for d, _ in history])
    y = np.array([v for _, v in history])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    sigma2 = float(resid @ resid) / max(1, len(y) - X.shape[1])
    cov = np.linalg.inv(X.T @ X)
    targets = days if granularity == "daily" else sorted({date(d.year, d.month, 15) for d in days}) \
        if granularity == "monthly" else sorted({date(d.year, 7, 1) for d in days})
    out = []
    for d in targets:
        x = np.array(features(d))
        mean = float(x @ beta)
        half = 1.2816 * math.sqrt(sigma2 * (1 + float(x @ cov @ x)))  # 80% interval
        day = d if granularity == "daily" else date(d.year, d.month if granularity == "monthly" else 1, 1)
        out.append(_point(day, mean, mean - half, mean + half, "trend", growth_per_year=round(float(beta[1]), 4)))
    return out


def climate_projection(place, history: list[tuple[date, float]], days: list[date], granularity: str,
                       log: SourceLog) -> list[dict]:
    """Delta method: observed monthly baseline (2019-2025) + each model's change from its own 2019-2025 baseline."""
    if not history:
        return []
    last_year = max(d.year for d in days)
    data = log.get(CLIMATE_URL, {"latitude": place.lat, "longitude": place.lon, "start_date": "2019-01-01",
                                 "end_date": f"{last_year}-12-31", "models": ",".join(CMIP6_MODELS),
                                 "daily": "temperature_2m_mean"}, "cmip6-highresmip",
                   f"CMIP6 HighResMIP temperature projections for {place.label}")["daily"]
    obs: dict[int, list[float]] = defaultdict(list)
    for d, v in history:
        obs[d.month].append(v)
    obs_mean = {m: statistics.fmean(v) for m, v in obs.items()}
    wanted_months = sorted({(d.year, d.month) for d in days})
    per_model: dict[str, dict[tuple, float]] = {}
    for model in CMIP6_MODELS:
        series = data.get(f"temperature_2m_mean_{model}") or []
        base, target = defaultdict(list), defaultdict(list)
        for stamp, v in zip(data["time"], series):
            if v is None:
                continue
            d = date.fromisoformat(stamp)
            if d.year <= 2025:
                base[d.month].append(v)
            if (d.year, d.month) in set(wanted_months):
                target[(d.year, d.month)].append(v)
        if base and target:
            per_model[model] = {ym: statistics.fmean(target[ym]) - statistics.fmean(base[ym[1]])
                                for ym in wanted_months if target.get(ym) and base.get(ym[1])}
    monthly = {}
    for ym in wanted_months:
        if ym[1] not in obs_mean:
            continue
        values = [obs_mean[ym[1]] + deltas[ym] for deltas in per_model.values() if ym in deltas]
        if values:
            monthly[ym] = values
    if granularity == "yearly":
        years = sorted({y for y, _ in monthly})
        out = []
        for y in years:
            months = [monthly[ym] for ym in monthly if ym[0] == y]
            if len(months) == 12:
                model_means = [statistics.fmean(m[i] for m in months) for i in range(min(len(m) for m in months))]
                out.append(_point(date(y, 1, 1), statistics.median(model_means), min(model_means), max(model_means),
                                  "climate_projection", models=len(model_means)))
        return out
    return [_point(date(y, m, 1), statistics.median(v), _pct(v, 0.1), _pct(v, 0.9), "climate_projection", models=len(v))
            for (y, m), v in sorted(monthly.items())]


# ---------------------------------------------------------------- orchestration

def granularity_for(plan: ForecastPlan) -> str:
    span = (plan.end - plan.start).days
    return "daily" if span <= 120 else "monthly" if span <= 5 * 366 else "yearly"


def forecast_series(metric: str, location: str, plan: ForecastPlan, today: date, log: SourceLog) -> dict:
    place = places.GLOBAL_PLACE if location == GLOBAL else _place(location)
    gran = granularity_for(plan)
    all_days = list(_days(plan.start.date(), plan.end.date()))
    points: list[dict] = []
    history, batches = None, []

    def get_history():
        nonlocal history, batches
        if history is None:
            history, batches = _history(metric, location, today)
        return history

    if METRICS[metric].trend_forecast:
        # Long global records: fit the last 30 years (or all of it) so the trend reflects current change.
        history, batches = _history(metric, location, today, date(max(METRICS[metric].first_year, today.year - 30), 1, 1))
        points = trend_fit(history, all_days, gran)
    elif gran == "daily":
        remaining = list(all_days)
        ahead = lambda d: (d - today).days
        if metric in ("temperature", "humidity", "precipitation"):
            ecmwf = [d for d in remaining if ahead(d) < 15]
            if ecmwf:
                points += ensemble(place, metric, ecmwf, "ecmwf_ifs025", log)
            gfs = [d for d in remaining if 15 <= ahead(d) < 35]
            if gfs:
                points += ensemble(place, metric, gfs, "gfs05", log)  # gfs025 only reaches ~10 days
        elif metric in AIR_VAR:
            near = [d for d in remaining if ahead(d) < 4]
            if near:
                points += cams(place, metric, near, log)
        elif metric == "streamflow" and place.kind == "modeled":  # GloFAS is modeled; don't splice it onto USGS gauge history
            near = [d for d in remaining if ahead(d) < 30]
            if near:
                points += glofas(place, near, log)
        covered = {p["time"][:10] for p in points}
        rest = [d for d in remaining if d.isoformat() not in covered]
        if rest:
            points += climatology(get_history(), rest, "daily")
    elif metric == "temperature" and plan.start.year > today.year:
        points = climate_projection(place, get_history(), all_days, gran, log)
    else:
        points = climatology(get_history(), all_days, gran)

    points.sort(key=lambda p: p["time"])
    methods = list(dict.fromkeys(p["method"] for p in points))
    vals = [p["value"] for p in points]
    summary = None
    if points:
        los = [p["lo"] for p in points if p["lo"] is not None]
        his = [p["hi"] for p in points if p["hi"] is not None]
        summary = {"avg": round(statistics.fmean(vals), 2), "min": round(min(vals), 2), "max": round(max(vals), 2),
                   "range_lo": round(min(los), 2) if los else None, "range_hi": round(max(his), 2) if his else None}
    return {"metric": metric, "location": location, "unit": metric_unit(metric), "granularity": gran,
            "start": plan.start.isoformat(), "end": plan.end.isoformat(), "count": len(points), "points": points,
            "methods": methods, "method_labels": [METHOD_LABEL[m] for m in methods], "summary": summary,
            "history_batches": [b["batch_id"] for b in batches]}


def recent_context(metric: str, location: str, today: date) -> list[dict]:
    """Last 7 days of observations, drawn before the forecast so the chart shows where it starts from."""
    from readings.service import get_readings
    end = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    try:
        r = get_readings(metric, location, end - timedelta(days=7), end)
    except DataUnavailable:
        return []
    daily: dict[str, list[float]] = defaultdict(list)
    for p in r["points"]:
        daily[p["time"][:10]].append(p["avg"])
    return [{"time": f"{d}T00:00:00+00:00", "value": round(statistics.fmean(v), 2), "forecast": False}
            for d, v in sorted(daily.items())]


def data_notes(plan: ForecastPlan, series: list[dict]) -> list[str]:
    notes = []
    for s in series:
        label = f"{metric_label(s['metric'])} · {plan.places.get(s['location'], {}).get('label', s['location'])}"
        if not s["points"]:
            notes.append(f"{label}: no forecast possible (not enough history for these dates).")
            continue
        notes.append(f"{label}: " + "; ".join(s["method_labels"]) + ".")
        if "climatology" in s["methods"]:
            notes.append("'Typical conditions' days show the median and 10th-90th percentile range seen on those "
                         "calendar dates in past years. They describe what is normal, not what will happen.")
        if "glofas" in s["methods"]:
            notes.append("GloFAS simulates natural river flow and may not reflect dams, reservoirs or water withdrawals.")
        if "cams" in s["methods"]:
            notes.append("Air-quality forecasts come from a single model run, so they have no uncertainty range.")
        if "trend" in s["methods"]:
            notes.append("The trend projection assumes the change of the last 30 years continues at the same rate; "
                         "the band is an 80% interval.")
        if "climate_projection" in s["methods"]:
            notes.append("Climate projections show the expected climate for that period, not the weather on a given day.")
    return list(dict.fromkeys(notes))
