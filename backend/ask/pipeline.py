"""The full question -> answer card flow from docs/full.png.

2  Gemini understands the question (parser.parse_query)
   -> valid? otherwise ask the user to rephrase
   -> route by time range
3/4 Tiger (recent) and/or Snowflake (historical), merged on time + location (readings.service)
5  Gemini analyzes: trends, recent vs historical, chart spec, answer text (ask.analyze)
7  ElevenLabs: audio_url for /voice/speak
8  Solana: hash of query + result + source + timestamp, anchored as a memo
6  Answer card for the UI

Instead of having Gemini write raw SQL here, the parsed metric/location/time range drive
parameterized queries in readings.service, so every query is read-only and valid by
construction. Free-form SQL stays available to Gemini through the MCP server.
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from google import genai

from parser import EnvironmentalQuery, parse_query
from readings.service import get_readings, recent_cutoff
from shared import places
from shared.catalog import CITIES, GLOBAL, METRICS, label as metric_label, unit as metric_unit
from shared.series import DataUnavailable
from tiger.repo import get_repo as get_tiger
from verify.hashing import build_record, memo_for, sha256_hex
from verify.solana_client import SolanaUnavailable, get_client as get_solana
from warehouse.repo import get_repo as get_warehouse
from warehouse.sample_data import HISTORY_START

from .analyze import analyze
from .factcheck import grounding_badge
from .cache import TTL_HISTORICAL, TTL_RECENT, TTL_UNDERSTAND, cache_key, get_cache, normalize
from .memory import get_store, new_conversation_id
from .transcribe import transcribe

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_SERIES = 4
BASELINE_YEARS = 5

_client: genai.Client | None = None


def get_gemini() -> genai.Client:
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise DataUnavailable("GEMINI_API_KEY is not set in backend/.env.local")
        _client = genai.Client(api_key=key)
    return _client


@dataclass
class Plan:
    pairs: list[tuple[str, str]]  # (metric, location) series to fetch
    start: datetime
    end: datetime
    operation: str
    places: dict = field(default_factory=dict)  # location key -> {label, kind, lat, lon, ...}

    @property
    def metrics(self) -> list[str]:
        return list(dict.fromkeys(m for m, _ in self.pairs))

    @property
    def locations(self) -> list[str]:
        return list(dict.fromkeys(l for _, l in self.pairs))

    def to_dict(self) -> dict:
        return {"metrics": self.metrics, "locations": self.locations, "start": self.start.isoformat(),
                "end": self.end.isoformat(), "operation": self.operation,
                "places": {k: {x: v[x] for x in ("label", "kind", "lat", "lon")} for k, v in self.places.items()}}


class NeedsClarification(Exception):
    pass


def _nice(location: str) -> str:
    return CITIES[location].name if location in CITIES else places.display_name(location)


def make_plan(q: EnvironmentalQuery, now: datetime) -> Plan:
    """The diagram's "Read-only & valid?" gate: everything must map onto data we actually have."""
    if not q.metrics:
        raise NeedsClarification(q.clarification_question or
                                 f"Which measurement do you mean? I have {', '.join(m.label for m in METRICS.values())}.")
    city_metrics = [m for m in dict.fromkeys(q.metrics) if not METRICS[m].global_only]
    global_metrics = [m for m in dict.fromkeys(q.metrics) if METRICS[m].global_only]
    names = [l for l in dict.fromkeys(q.locations) if places.slug(l) != GLOBAL]
    country_level = [m for m in city_metrics if METRICS[m].per_country]
    if country_level and not names and len(country_level) == len(city_metrics):
        names = ["World"]  # "global wildfire acreage"
    if city_metrics and not names:
        raise NeedsClarification(q.clarification_question or "Which place are you asking about?")
    resolved, unknown = [], []
    for name in names:  # any place on Earth: measured city, a place seen before, or geocoded now
        try:
            resolved.append(places.resolve(name))
        except places.PlaceNotFound:
            from ingest.global_series import burned_area_key
            if country_level and burned_area_key(name) in _area_keys():
                resolved.append(None)  # a region only country-level records know ("Southern Europe")
            else:
                unknown.append(name)
    if unknown:
        raise NeedsClarification(f"I couldn't find {', '.join(repr(u) for u in unknown)}. "
                                 f"Could you add the country or state?")
    cities = list(dict.fromkeys(p.key for p in resolved if p))
    earliest = min(date(METRICS[m].first_year, 1, 1) for m in q.metrics)

    operation = q.operation or "summary"
    try:
        start_day = date.fromisoformat(q.start_date) if q.start_date else None
        end_day = date.fromisoformat(q.end_date) if q.end_date else None
    except ValueError:
        raise NeedsClarification("I couldn't work out the time period. Could you give dates, like 'June 2023' "
                                 "or 'the last 7 days'?")

    end = now if end_day is None or end_day >= now.date() else \
        datetime.combine(end_day + timedelta(days=1), datetime.min.time(), timezone.utc)
    if start_day:
        start = datetime.combine(max(start_day, earliest), datetime.min.time(), timezone.utc)
    elif operation == "trend":  # "how fast is sea level rising?": use the whole record
        start = datetime.combine(earliest, datetime.min.time(), timezone.utc)
    else:
        # "Latest" looks back a day, except global CO2: Mauna Loa's daily values arrive 2-3 days late.
        latest_window = timedelta(days=7) if global_metrics else timedelta(hours=24)
        start = end - (latest_window if operation == "latest" else timedelta(days=7))
    if start >= end:
        raise NeedsClarification("That time period looks empty or in the future. Which dates do you mean?")

    # Global records (CO2, sea ice, sea level, global temperature) don't belong to a city.
    point_metrics = [m for m in city_metrics if not METRICS[m].per_country]
    pairs = [(m, l) for m in point_metrics for l in cities] + [(m, GLOBAL) for m in global_metrics]
    known = {p.key: p.to_dict() for p in resolved if p} | ({GLOBAL: places.GLOBAL_PLACE.to_dict()} if global_metrics else {})
    # Country-level records (burned area) are looked up by the country/region itself, not a point.
    for m in (m for m in city_metrics if METRICS[m].per_country):
        for name, place in zip(names, resolved):
            key, label = area_key(name, place)
            pairs.append((m, key))
            known[key] = {"label": label, "kind": "country", "lat": place.lat if place else 0.0,
                          "lon": place.lon if place else 0.0}
    return Plan(pairs[:MAX_SERIES], start, end, operation, known)


def area_key(name: str, place) -> tuple[str, str]:
    """'Canada' / 'Europe' / 'World' -> the stored country-or-region key for country-level records."""
    from ingest.global_series import burned_area_key
    available = _area_keys()
    for candidate in (name.split(",")[0], place.name if place else "", place.country if place else ""):
        key = burned_area_key(candidate) if candidate else ""
        if key in available:
            return key, candidate
    raise NeedsClarification(f"Burned area is recorded per country or world region (for example Canada, Spain, "
                             f"Europe or World), not for {name}. Which country do you mean?")


_AREA_KEYS: set[str] | None = None


def _area_keys() -> set[str]:
    global _AREA_KEYS
    if _AREA_KEYS is None:
        from warehouse.repo import get_repo as get_warehouse
        rows = get_warehouse()._safe_query("SELECT DISTINCT LOCATION FROM DAILY_READINGS WHERE METRIC = 'burned_area'")
        _AREA_KEYS = {r["location"] for r in rows}
    return _AREA_KEYS


MODELED_SOURCE = {"pm25": "Copernicus CAMS", "o3": "Copernicus CAMS", "no2": "Copernicus CAMS",
                  "temperature": "ECMWF ERA5 and weather-model analysis", "humidity": "ECMWF ERA5 and weather-model analysis",
                  "streamflow": "GloFAS (nearest modeled river)", "precipitation": "ECMWF ERA5 (daily totals)",
                  "dust": "Copernicus CAMS"}
GLOBAL_SOURCE = {
    "co2": "the global background level measured at Mauna Loa, Hawaii (NOAA GML); it is not city-specific",
    "global_temperature": "NOAA GlobalTemp: the global land and ocean average, as a departure from the 1901-2000 "
                          "average (not a local temperature)",
    "arctic_sea_ice": "NSIDC Sea Ice Index daily extent (area of ocean with at least 15% ice)",
    "antarctic_sea_ice": "NSIDC Sea Ice Index daily extent (area of ocean with at least 15% ice)",
    "sea_level": "NOAA satellite altimetry: global mean sea level relative to the 1993-2012 average; local sea level "
                 "can differ",
}


def data_notes(plan: Plan, sources: list[dict]) -> list[str]:
    """Where each series comes from, so the answer can say so (e.g. that CO2 is global, or data is modeled)."""
    notes = []
    for m, l in plan.pairs:
        if METRICS[m].per_country:
            notes.append(f"Burned area is the yearly total for {plan.places.get(l, {}).get('label', l)} from the "
                         f"Copernicus Global Wildfire Information System (via Our World in Data). Only "
                         f"{date.today().year} is partial (year-to-date); earlier years are complete.")
            continue
        if m in ("precipitation", "dust"):
            notes.append(f"{_nice(l)} {metric_label(m).lower()} values are modeled estimates from {MODELED_SOURCE[m]}.")
            if m == "precipitation":
                notes.append("Precipitation is shown in mm per day; totals are the sum of daily values.")
            continue
        place = places.get(l)
        if place and place.kind == "modeled":
            if m in MODELED_SOURCE:
                notes.append(f"{place.label} {metric_label(m).lower()} values are modeled estimates from "
                             f"{MODELED_SOURCE[m]}, not local monitor readings.")
            else:
                notes.append(f"No global source for {metric_label(m).lower()}; it is only available for measured US cities.")
            if m in ("pm25", "o3", "no2"):
                notes.append("Modeled air-quality history starts August 2022 outside Europe (2019 in Europe).")
            if m == "streamflow":
                notes.append("GloFAS simulates natural river flow and may not reflect dams, reservoirs or water withdrawals.")
            continue
        if l == GLOBAL:
            notes.append(f"{metric_label(m)} is {GLOBAL_SOURCE.get(m, 'a global record')}.")
        elif m in ("temperature", "humidity"):
            notes.append(f"{_nice(l)} weather is from the {CITIES[l].notes['weather']} station (NOAA).")
        elif m in ("streamflow", "water_temperature"):
            notes.append(f"{_nice(l)} {metric_label(m).lower()} is from the USGS gauge on the {CITIES[l].notes['usgs']}.")
        elif l in CITIES and "air" in CITIES[l].notes:
            notes.append(f"{_nice(l)} air quality averages {CITIES[l].notes['air']} (EPA).")
    from ingest.global_sources import AREA_MIN_KM
    for l in dict.fromkeys(l for _, l in plan.pairs):
        place = places.get(l)
        if place and place.kind == "modeled" and (place.radius_km or 0) > AREA_MIN_KM:
            notes.append(f"Modeled values for {place.label} are averaged over up to 9 land points across its central "
                         f"area (about 450 km around its center), not a single location.")
    preliminary = sorted({s["source"] for s in sources if s["quality"] == "preliminary"})
    if preliminary:
        notes.append(f"Some values come from real-time feeds ({', '.join(preliminary)}) that are preliminary "
                     f"and may still be revised by the agency.")
    return list(dict.fromkeys(notes))


def _shift_years(t: datetime, years: int) -> datetime:
    try:
        return t.replace(year=t.year - years)
    except ValueError:  # Feb 29
        return t.replace(year=t.year - years, day=28)


def fetch(plan: Plan) -> tuple[list[dict], list[dict], list[str]]:
    """Series for the plan, historical baselines if asked, and every source batch the numbers came from."""
    batch_ids: set[str] = set()

    def read(m: str, l: str, s: datetime, e: datetime) -> dict:
        result = get_readings(m, l, s, e)
        batch_ids.update(b["batch_id"] for b in result.get("batches", []))
        return result

    series = [read(m, l, plan.start, plan.end) for m, l in plan.pairs]
    if (plan.end - plan.start).days >= 3 * 365:
        for s in series:
            s.update(long_term(s["metric"], s["location"], plan.start, plan.end))
    baselines = []
    if plan.operation == "compare_history":
        for m, l in plan.pairs:
            by_year = []
            for y in range(1, BASELINE_YEARS + 1):
                s, e = _shift_years(plan.start, y), _shift_years(plan.end, y)
                first = date(METRICS[m].first_year, 1, 1)
                if e.date() <= first:
                    break
                past = read(m, l, max(s, datetime.combine(first, datetime.min.time(), timezone.utc)), e)
                if past["summary"]:
                    by_year.append({"year": s.year, "avg": past["summary"]["avg"], "max": past["summary"]["max"]})
            if by_year:
                baselines.append({"metric": m, "location": l, "unit": metric_unit(m), "by_year": by_year,
                                  "baseline_avg": round(sum(b["avg"] for b in by_year) / len(by_year), 2)})
    return series, baselines, sorted(batch_ids)


def long_term(metric: str, location: str, start: datetime, end: datetime) -> dict:
    """Year-by-year statistics and the trend across complete years, for questions spanning years."""
    import numpy as np
    from warehouse.repo import THRESHOLDS, get_repo as get_warehouse, yearly_stats
    try:
        years = yearly_stats(get_warehouse(), metric, location, start, end)
    except DataUnavailable:
        return {}
    if len(years) < 3:
        return {"yearly": years} if years else {}
    this_year = date.today().year
    full = [y for y in years if y.get("complete") and y["year"] < this_year]  # skip partial years
    years = [{k: v for k, v in y.items() if k != "complete"} for y in years]
    full = [y for y in years if y["year"] in {f["year"] for f in full}]
    out = {"yearly": years}
    if len(full) >= 3:
        xs = np.array([y["year"] for y in full], float)
        per_decade = lambda key: round(float(np.polyfit(xs, np.array([y[key] for y in full], float), 1)[0]) * 10, 3)
        slope = per_decade("mean") / 10
        out["long_term"] = {
            "first_full_year": full[0]["year"], "first_full_year_mean": full[0]["mean"],
            "last_full_year": full[-1]["year"], "last_full_year_mean": full[-1]["mean"],
            "change_between_them": round(full[-1]["mean"] - full[0]["mean"], 2),
            "trend_per_decade": round(slope * 10, 3),
            "highest_year": max(full, key=lambda y: y["mean"])["year"],
            "lowest_year": min(full, key=lambda y: y["mean"])["year"],
            "partial_years_excluded": [y["year"] for y in years if y not in full],
            "most_extreme_day_trend_per_decade": per_decade("highest"),
            "highest_single_day": max(full, key=lambda y: y["highest"])["highest"],
            "highest_single_day_year": max(full, key=lambda y: y["highest"])["year"],
        }
        if all("days_above_threshold" in y for y in full):
            out["long_term"]["days_above_threshold_trend_per_decade"] = per_decade("days_above_threshold")
            out["long_term"]["first_full_year_days_above"] = full[0]["days_above_threshold"]
            out["long_term"]["last_full_year_days_above"] = full[-1]["days_above_threshold"]
        if metric in THRESHOLDS:
            out["long_term"]["threshold"] = THRESHOLDS[metric][2]
    return out


def load_places(plan: Plan) -> dict:
    from ingest.on_demand import ensure
    loaded = {}
    for key, info in plan.places.items():
        if info["kind"] in ("modeled", "measured"):
            metrics = [m for m, l in plan.pairs if l == key]
            result = ensure(places.get(key), metrics, plan.start.date())
            if any(result.values()):
                loaded[key] = result
    return loaded


def provenance(batch_ids: list[str]) -> tuple[list[dict], str | None]:
    """Registry entries (agency, dataset, Solana anchor) for the batches behind an answer."""
    try:
        from ingest.verify import batch_info
        return batch_info(batch_ids), None
    except Exception as e:  # provenance lookup must never block an answer
        return [], f"provenance lookup failed: {str(e)[:120]}"


def build_chart(choice, series: list[dict], baselines: list[dict]) -> dict:
    label = lambda s: f"{metric_label(s['metric'])} · {_nice(s['location'])}"
    chart = {"type": choice.type, "title": choice.title, "y_label": choice.y_label}
    if choice.type == "line" or not any(s["summary"] for s in series):
        chart |= {"type": "line", "x_label": "Time", "series": [
            {"name": label(s), "unit": s["unit"], "granularity": s["granularity"],
             "points": [{"time": p["time"], "value": p["avg"], "source": p.get("source")} for p in s["points"]]}
            for s in series]}
    elif baselines and len(series) == 1:
        b = baselines[0]
        bars = [{"label": str(y["year"]), "value": y["avg"]} for y in reversed(b["by_year"])]
        bars.append({"label": f"{series[0]['start'][:4]} (selected period)", "value": series[0]["summary"]["avg"], "highlight": True})
        chart |= {"x_label": "Year", "bars": bars}
    else:
        chart |= {"x_label": "", "bars": [{"label": label(s), "value": s["summary"]["avg"]} for s in series if s["summary"]]}
    return chart


def anchor(question: str, analysis, series: list[dict], sources: list[dict], fact: dict) -> dict:
    """Step 8: SHA-256 of query + result + source + timestamp, written to Solana as a memo.

    `source` commits to the exact agency batches (by their anchored manifest hashes), so the
    answer's proof chains back to the source data's proof.
    """
    stores = sorted({src for s in series for src in s.get("sources", {})})
    modes = {"tiger": get_tiger().mode, "snowflake": get_warehouse().mode}
    record = build_record(
        query=question,
        result={"answer": analysis.answer_text,
                "series": [{k: s[k] for k in ("metric", "location", "route", "sources", "summary")} for s in series],
                # the grounding check, and a fingerprint of the exact data Gemini was given
                "fact_check": {k: fact[k] for k in ("ok", "checked", "unsupported", "evidence_sha256")}},
        source=json.dumps({"stores": {s: modes[s] for s in stores},
                           "batches": [{"batch_id": b["batch_id"], "source": b["source"],
                                        "manifest_sha256": b["manifest_sha256"]} for b in sources]},
                          sort_keys=True, separators=(",", ":")),
    )
    digest = sha256_hex(record)
    solana = get_solana()
    try:
        tx = solana.send_memo(memo_for(digest))
    except SolanaUnavailable as e:
        # Still answer the question; just don't claim it's verified.
        return {"record": record, "hash": digest, "signature": None, "explorer_url": None, "mode": solana.mode,
                "cluster": solana.cluster, "error": str(e), "badge": {"verified": False, "label": "Not verified"}}
    label = "Verified on Solana" if solana.mode == "rpc" else "Verified (simulated)"
    return {"record": record, "hash": digest, "signature": tx.signature, "explorer_url": tx.explorer_url,
            "mode": solana.mode, "cluster": tx.cluster, "slot": tx.slot,
            "badge": {"verified": True, "label": label}}


def unsupported_message(topic: str) -> str:
    """Say plainly that the data isn't there (instead of implying the question was unclear), and what is."""
    return (f"Ecuery doesn't have {topic} data yet. It can answer about air quality (PM2.5, ozone, NO2), weather "
            f"(temperature, humidity), rivers, global CO2, and disasters like tornadoes, earthquakes, wildfires "
            f"and hurricanes, for places worldwide, past or forecast.")


def _last_day(end: datetime) -> str:
    """Plans use an exclusive end; the parser (and follow-ups) speak in inclusive end dates."""
    return (end - timedelta(microseconds=1)).date().isoformat()


def _ask_forecast(client, question, voice, parsed, understood, conversation, history, now, hits, lap, timings) -> dict:
    from .events_answer import NeedsClarification as EventClarification, build_likelihood_card, make_event_plan
    from .forecast import NeedsClarification as ForecastClarification, make_forecast_plan
    from .forecast_answer import build_forecast_card

    memory, cache, conversation_id = get_store(), get_cache(), conversation["conversation_id"]

    def clarify(message: str) -> dict:
        memory.append(conversation_id, {"question": question, "understood": understood, "reply": message})
        return {"status": "needs_clarification", "question": question, "clarification": message,
                "understood": understood, **conversation, "timings": timings}

    if parsed.clarification_question:  # e.g. asked about rain, which Ecuery can't forecast
        return clarify(parsed.clarification_question)
    events_only = parsed.event_types and not parsed.metrics  # "will the river flood" -> river-flow forecast instead
    try:
        plan = make_event_plan(parsed, now, future=True) if events_only else make_forecast_plan(parsed, now, MAX_SERIES)
    except (EventClarification, ForecastClarification) as e:
        return clarify(str(e))

    analysis_question = question if not history else f"{question} (follow-up to: {history[-1]['question']})"
    # Forecasts change as models update; cache briefly (weather models rerun every 6 hours).
    answer_key = cache_key("answer", {"q": normalize(question), "forecast": plan.to_dict(), "model": MODEL,
                                      "today": now.date().isoformat()})
    card = cache.get(answer_key)
    hits["answer"] = card is not None
    if card is None:
        builder = build_likelihood_card if events_only else build_forecast_card
        card = builder(client, MODEL, question, analysis_question, plan, provenance, lap, now)
        if card["verification"]["badge"]["verified"] and card["fact_check"]["ok"]:
            cache.set(answer_key, card, TTL_RECENT * 6)
    else:
        lap("answer_cache")

    remembered = {"start_date": plan.start.date().isoformat(), "end_date": _last_day(plan.end), "operation": "forecast"}
    if events_only:
        remembered |= {"event_types": plan.types, "locations": [plan.place["key"]] if plan.place else []}
    else:
        remembered |= {"metrics": plan.metrics, "locations": [l for l in plan.locations if l != GLOBAL]}
    memory.append(conversation_id, {"question": question, "understood": understood | remembered,
                                    "reply": card["answer_text"]})
    return {"status": "answered", "question": question, **conversation, "understood": understood,
            "plan": plan.to_dict(), **card,
            "audio_url": "/voice/speak?" + urlencode({"text": card["answer_text"], "voice": voice}),
            "timings": timings}


def _ask_events(client, question, voice, parsed, understood, conversation, history, now, hits, lap, timings) -> dict:
    from .events_answer import NeedsClarification as EventClarification, build_card, make_event_plan

    memory, cache, conversation_id = get_store(), get_cache(), conversation["conversation_id"]
    try:
        plan = make_event_plan(parsed, now)
    except EventClarification as e:
        memory.append(conversation_id, {"question": question, "understood": understood, "reply": str(e)})
        return {"status": "needs_clarification", "question": question, "clarification": str(e),
                "understood": understood, **conversation, "timings": timings}

    # Past years don't change; anything reaching the last day can gain events.
    ttl = TTL_HISTORICAL if plan.end < now - timedelta(days=1) else TTL_RECENT
    answer_key = cache_key("answer", {"q": normalize(question), "events": plan.to_dict(), "model": MODEL})
    card = cache.get(answer_key)
    hits["answer"] = card is not None
    if card is None:
        analysis_question = question if not history else f"{question} (follow-up to: {history[-1]['question']})"
        card = build_card(client, MODEL, question, analysis_question, plan, provenance, lap)
        if card["verification"]["badge"]["verified"] and card["fact_check"]["ok"]:
            cache.set(answer_key, card, ttl)
    else:
        lap("answer_cache")

    memory.append(conversation_id, {
        "question": question,
        "understood": understood | {"event_types": plan.types, "locations": [plan.place["key"]] if plan.place else [],
                                    "start_date": plan.start.date().isoformat(), "end_date": _last_day(plan.end),
                                    "operation": plan.operation},
        "reply": card["answer_text"],
    })
    return {"status": "answered", "question": question, **conversation, "understood": understood,
            "plan": plan.to_dict(), **card,
            "audio_url": "/voice/speak?" + urlencode({"text": card["answer_text"], "voice": voice}),
            "timings": timings}


TTL_WEB = 7 * 24 * 3600


def _ask_web(client, question, voice, parsed, understood, conversation, history, hits, lap, timings) -> dict | None:
    """No dataset covers this topic: a cited, quote-checked answer from the web (ask/web_answer.py), or None."""
    from .web_answer import WebUnavailable, answer_from_web

    if os.getenv("ECUERY_WEB_FALLBACK", "1") == "0":
        return None
    memory, cache, conversation_id = get_store(), get_cache(), conversation["conversation_id"]
    answer_key = cache_key("answer", {"q": normalize(question), "web": parsed.unsupported_topic, "model": MODEL})
    card = cache.get(answer_key)
    hits["answer"] = card is not None
    if card is None:
        analysis_question = question if not history else f"{question} (follow-up to: {history[-1]['question']})"
        try:
            card = answer_from_web(client, MODEL, analysis_question, parsed.unsupported_topic, lap)
        except WebUnavailable as e:
            timings["web_fallback"] = str(e)
            return None
        if card["verification"]["badge"]["verified"]:
            cache.set(answer_key, card, TTL_WEB)
    else:
        lap("answer_cache")
    memory.append(conversation_id, {"question": question, "understood": understood, "reply": card["answer_text"]})
    return {"status": "answered", "question": question, **conversation, "understood": understood,
            "plan": {"source": "web", "topic": parsed.unsupported_topic}, **card,
            "audio_url": "/voice/speak?" + urlencode({"text": card["answer_text"], "voice": voice}),
            "timings": timings}


def ask_voice(audio: bytes, mime_type: str, voice: str = "rachel", conversation_id: str | None = None) -> dict:
    """Step 1: a recorded question. Transcribe it, then run the same flow as a typed question."""
    started = time.perf_counter()
    transcript = transcribe(get_gemini(), MODEL, audio, mime_type)
    took = round(time.perf_counter() - started, 2)
    if not transcript:
        return {"status": "needs_clarification", "transcript": "",
                "conversation_id": conversation_id or new_conversation_id(),
                "clarification": "I didn't catch that. Could you try again a little closer to the mic?",
                "timings": {"transcribe": took}}
    card = ask(transcript, voice, conversation_id)
    return {"transcript": transcript, **card, "timings": {"transcribe": took, **card["timings"]}}


def ask(question: str, voice: str = "rachel", conversation_id: str | None = None) -> dict:
    timings: dict[str, float] = {}
    t = time.perf_counter()

    def lap(name: str):
        nonlocal t
        now = time.perf_counter()
        timings[name] = round(now - t, 2)
        t = now

    memory = get_store()
    conversation_id = conversation_id or new_conversation_id()
    history = memory.history(conversation_id)

    client = get_gemini()
    cache = get_cache()
    hits = {}
    # 5-minute steps: the same question a minute later maps to the same window (and cache entries).
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    now -= timedelta(minutes=now.minute % 5)

    understand_key = cache_key("understand", {"q": normalize(question), "today": now.date().isoformat(), "model": MODEL,
                                              "previous": history[-1]["understood"] if history else None})
    cached = cache.get(understand_key)
    hits["understand"] = cached is not None
    if cached:
        parsed = EnvironmentalQuery.model_validate(cached)
    else:
        parsed = parse_query(client, question, today=now.date(), model=MODEL, history=history)
        cache.set(understand_key, parsed.model_dump(), TTL_UNDERSTAND)
    lap("understand")
    understood = {k: v for k, v in parsed.model_dump().items()
                  if k in ("intent", "metrics", "event_types", "locations", "start_date", "end_date", "operation",
                           "radius_km", "min_magnitude") and v not in (None, [])}
    conversation = {"conversation_id": conversation_id, "turn": len(history) + 1, "memory": memory.mode, "cache": hits}

    if parsed.unsupported_topic and not parsed.metrics and not parsed.event_types:
        web = _ask_web(client, question, voice, parsed, understood, conversation, history, hits, lap, timings)
        if web:
            return web
        message = unsupported_message(parsed.unsupported_topic)
        memory.append(conversation_id, {"question": question, "understood": understood, "reply": message})
        return {"status": "needs_clarification", "question": question, "clarification": message,
                "unsupported_topic": parsed.unsupported_topic, "understood": understood, **conversation,
                "timings": timings}

    from .forecast import wants_forecast
    if wants_forecast(parsed, now.date()):  # the future: forecasts, outlooks, likelihood of events
        return _ask_forecast(client, question, voice, parsed, understood, conversation, history, now, hits, lap, timings)
    if parsed.event_types:  # disasters / events: a different kind of data than readings
        return _ask_events(client, question, voice, parsed, understood, conversation, history, now, hits, lap, timings)

    try:
        plan = make_plan(parsed, now)
    except NeedsClarification as e:
        memory.append(conversation_id, {"question": question, "understood": understood, "reply": str(e)})
        return {"status": "needs_clarification", "question": question, "clarification": str(e),
                "understood": understood, **conversation, "timings": timings}

    ttl = TTL_HISTORICAL if plan.end <= recent_cutoff() else TTL_RECENT
    answer_key = cache_key("answer", {"q": normalize(question), "plan": plan.to_dict(), "model": MODEL})
    card = cache.get(answer_key)
    hits["answer"] = card is not None
    if card is None:
        data_key = cache_key("data", plan.to_dict())
        cached_data = cache.get(data_key)
        hits["data"] = cached_data is not None
        if cached_data:
            series, baselines, batch_ids = cached_data["series"], cached_data["baselines"], cached_data["batch_ids"]
        else:
            # A place nobody asked about before: fetch, fingerprint, anchor and store its data first.
            loaded = load_places(plan)
            if loaded:
                lap("load_place")
            series, baselines, batch_ids = fetch(plan)
            if not any(s["warnings"] for s in series):  # never cache a result with a store missing
                cache.set(data_key, {"series": series, "baselines": baselines, "batch_ids": batch_ids}, ttl)
        lap("fetch")

        # Give Gemini's analysis the earlier question too, so "what about Philadelphia?" reads naturally.
        analysis_question = question if not history else f"{question} (follow-up to: {history[-1]['question']})"
        sources, provenance_error = provenance(batch_ids)
        analysis, fact = analyze(client, MODEL, analysis_question, plan.to_dict() | {"data_notes": data_notes(plan, sources)},
                           series, baselines)
        lap("analyze")
        verification = anchor(question, analysis, series, sources, fact)
        lap("verify")
        card = {
            "answer_text": analysis.answer_text,
            "trends": analysis.trends,
            "comparison": analysis.comparison,
            "chart": build_chart(analysis.chart, series, baselines),
            "data": [{k: s[k] for k in ("metric", "location", "unit", "route", "granularity", "sources", "warnings", "summary")}
                     for s in series],
            "historical_baselines": baselines,
            "data_notes": data_notes(plan, sources),
            "provenance": sources,
            **({"provenance_error": provenance_error} if provenance_error else {}),
            "verification": verification,
            "fact_check": fact,
            "grounding": grounding_badge(fact),
        }
        # Only cache complete, verified, grounded answers; a cached answer reuses its original Solana proof.
        if verification["badge"]["verified"] and fact["ok"] and not any(d["warnings"] for d in card["data"]):
            cache.set(answer_key, card, ttl)
    else:
        lap("answer_cache")

    # Remember what was actually answered (resolved dates, not "last week") for the next follow-up.
    memory.append(conversation_id, {
        "question": question,
        "understood": understood | {"metrics": plan.metrics, "locations": plan.locations,
                                    "start_date": plan.start.date().isoformat(),
                                    "end_date": _last_day(plan.end), "operation": plan.operation},
        "reply": card["answer_text"],
    })

    return {
        "status": "answered",
        "question": question,
        **conversation,
        "understood": understood,
        "plan": plan.to_dict(),
        **card,
        "audio_url": "/voice/speak?" + urlencode({"text": card["answer_text"], "voice": voice}),
        "timings": timings,
    }
