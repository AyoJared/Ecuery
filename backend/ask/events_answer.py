"""Answering event questions: "how many tornadoes hit Philly in 2025", "biggest earthquakes this year", ...

Same flow as readings (understand -> route -> fetch -> Gemini analysis -> Solana), but the data are
events searched within a radius of a place (or worldwide), loaded on demand by ingest/events.py.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from google import genai
from google.genai import types as gtypes

from ingest import events as ev
from shared import places
from verify.hashing import build_record, memo_for, sha256_hex
from verify.solana_client import SolanaUnavailable, get_client as get_solana

from .analyze import Analysis
from .factcheck import grounded, grounding_badge

US_ONLY = {"noaa-storm-events"}
TYPE_LABEL = ev.EVENT_TYPES

INSTRUCTIONS = """You are Ecuery, an environmental data assistant answering a question about natural disasters or
weather events. Use ONLY the data provided: exact counts, totals and the listed events. Never invent events or numbers.
Lead with the direct answer (e.g. "No tornadoes touched down in Philadelphia in 2025."). If the count is zero or small,
mention the nearest events outside the search area from "nearest", with distance, date, strength and place.
Name the strongest or most damaging events with dates. Give tornado ratings as EF0-EF5 and earthquake magnitudes as M.
If rank is set, "biggest" is sorted by it (deaths, damage, fastest 24-hour strengthening, duration): name the top
events by that measure. For tropical cyclones give the category, peak wind (kt) and, when relevant, minimum pressure,
fastest 24-hour strengthening or duration from details. For questions about change over time ("getting stronger",
"moving north", "more frequent") use by_year (count, mean_magnitude, max_magnitude, mean_lat, mean_duration_days)
and trends_per_decade, comparing early and recent decades; never claim a cause.
Mention the search area and data source in a short clause (if search.within is set, say "in <within>" and
do not mention a radius), and any note in "data_notes" that changes the meaning
(e.g. that a source only covers the US or runs a few months behind). 2-4 plain sentences: no markdown or bullets,
it will be read aloud. Write numbers as digits (36.2 km, EF1, 2025), not words. For the chart, choose a bar chart titled for event counts over time."""


class NeedsClarification(Exception):
    pass


@dataclass
class EventPlan:
    types: list[str]
    start: datetime
    end: datetime
    operation: str
    place: dict | None = None           # places.Place.to_dict(), or None for worldwide
    radius_km: float | None = None
    min_magnitude: float | None = None
    sources: list[str] = field(default_factory=list)
    region: dict | None = None          # keep state/country searches inside their borders (see ingest/events._base)
    basins: list[str] | None = None     # IBTrACS basin codes
    basin_name: str | None = None
    name: str | None = None             # a named storm
    rank_by: str = "magnitude"

    def to_dict(self) -> dict:
        return {"event_types": self.types, "start": self.start.isoformat(), "end": self.end.isoformat(),
                "operation": self.operation, "place": self.place and {k: self.place[k] for k in ("key", "label", "lat", "lon")},
                "radius_km": self.radius_km, "min_magnitude": self.min_magnitude, "sources": self.sources,
                "within": self.region and self.region["name"], "basin": self.basin_name, "event_name": self.name,
                "rank": self.rank_by}

    def query_kw(self) -> dict:
        return {"min_magnitude": self.min_magnitude, "sources": self.sources or ["none"], "region": self.region,
                "basins": self.basins, "name": self.name}


def make_event_plan(q, now: datetime, future: bool = False) -> EventPlan:
    types = list(dict.fromkeys(q.event_types))
    names = [l for l in dict.fromkeys(q.locations) if places.slug(l) != places.GLOBAL]
    basin_name = getattr(q, "basin", None)
    if "hurricane" in types and not basin_name:  # "Western Pacific typhoons" parsed as a place
        basin_name = next((n for n in names if ev.basin_codes(n)), None)
    basins = ev.basin_codes(basin_name) if basin_name else None
    if basins:
        names = [n for n in names if not ev.basin_codes(n)]
    else:
        basin_name = None
    rank_by = getattr(q, "rank_by", None) or "magnitude"
    event_name = getattr(q, "event_name", None)
    if event_name:
        for word in ("hurricane", "typhoon", "tropical storm", "cyclone", "super typhoon", "storm"):
            if event_name.lower().startswith(word + " "):
                event_name = event_name[len(word) + 1:]
        event_name = event_name.strip() or None
    place = None
    if names:
        try:
            place = places.resolve(names[0])
        except places.PlaceNotFound:
            raise NeedsClarification(f"I couldn't find '{names[0]}'. Could you add the country or state?")

    try:
        start_day = date.fromisoformat(q.start_date) if q.start_date else None
        end_day = date.fromisoformat(q.end_date) if q.end_date else None
    except ValueError:
        raise NeedsClarification("I couldn't work out the time period. Could you give a year or dates?")
    day0 = lambda d: datetime.combine(d, datetime.min.time(), timezone.utc)
    if future:  # likelihood of events in an upcoming window (default: the next 12 months)
        start = day0(max(start_day or now.date() + timedelta(days=1), now.date()))
        end = day0(end_day + timedelta(days=1)) if end_day else start + timedelta(days=365)
    else:
        end = now if end_day is None or end_day >= now.date() else day0(end_day + timedelta(days=1))
        start = day0(start_day) if start_day else end - timedelta(days=365 if not event_name else 365 * 60)
    if start >= end:
        raise NeedsClarification("That time period looks empty or in the future. Which dates do you mean?")

    sources = sorted({s for t in types for s in ev.TYPE_SOURCES.get(t, [])})
    if rank_by in ("deaths", "damage"):  # casualty/damage figures live in impact databases
        impact = sorted({s for t in types for s in ev.IMPACT_SOURCES.get(t, [])})
        sources = impact + [s for s in sources if s not in ("usgs-earthquakes",)] if impact else sources
    if place and (place.country_code or "").upper() != "US":
        sources = [s for s in sources if s not in US_ONLY]
    if sources and not future:  # "on record" / 1850: start where the data does
        first = min(ev.FIRST_YEAR[s] for s in sources)
        start = max(start, datetime(first, 1, 1, tzinfo=timezone.utc))
        if start >= end:
            raise NeedsClarification(f"Records for that start in {first}. Could you pick a later period?")
    radius = (q.radius_km or ev.default_radius(types, place.radius_km)) if place else None
    region = None
    if place and not q.radius_km and place.feature_code in ("state", "province", "region") and place.country_code == "US":
        region = {"name": place.name, "pattern": f"%, {place.name}", "sources": ["noaa-storm-events"]}
    elif place and not q.radius_km and place.feature_code == "country" and place.country_code != "US":
        region = {"name": place.name, "pattern": f"%{place.name}%",
                  "sources": ["usgs-earthquakes", "noaa-sig-earthquakes", "gdacs"]}
    return EventPlan(types, start, end, q.operation or "count", place.to_dict() if place else None,
                     round(radius, 1) if radius else None, q.min_magnitude, sources, region,
                     basins, basin_name, event_name, rank_by)


DETAIL_KEYS = ("sshs_peak", "min_pressure_mb", "max_intensification_24h_kt", "duration_days", "basin", "alertlevel",
               "damage_scale", "depth_km")


def _event_view(r: dict) -> dict:
    details = r["details"] or {}
    extra = {k: details[k] for k in DETAIL_KEYS if details.get(k) is not None}
    return {"id": f"{r['source']}:{r['event_id']}", "type": r["type"], "name": r["name"],
            "date": r["starts_at"].date().isoformat(), "strength": r["magnitude_label"], "magnitude": r["magnitude"],
            "region": r["region"], "distance_km": round(r["distance_km"], 1) if r.get("distance_km") is not None else None,
            "deaths": r["deaths"], "injuries": r["injuries"], "damage_usd": r["damage_usd"],
            "path_miles": float(details["TOR_LENGTH"]) if details.get("TOR_LENGTH") else None,
            "lat": r["lat"], "lon": r["lon"], "source": r["source"], "batch_id": r["batch_id"],
            **({"details": extra} if extra else {})}


def fetch_events(plan: EventPlan) -> dict:
    loaded = ev.ensure_events(plan.types, plan.start, plan.end, plan.sources) if plan.sources else {}
    p = plan.place
    geo = (p["lat"], p["lon"], plan.radius_km) if p else (None, None, None)
    args = (plan.types, plan.start, plan.end, *geo)
    kw = plan.query_kw()
    summary = ev.summarize_events(*args, **kw)
    biggest = [_event_view(r) for r in ev.find_events(*args, limit=15, order=plan.rank_by, **kw)]
    nearest = []
    if p and summary["count"] < 3:
        wider = max(500.0, (plan.radius_km or 0) * 4)
        nearest = [_event_view(r) for r in ev.nearest_events(plan.types, plan.start, plan.end, p["lat"], p["lon"],
                                                              limit=summary["count"] + 3, max_km=wider, **kw)
                   if r["distance_km"] > (plan.radius_km or 0)][:3]
    map_points = [_event_view(r) for r in ev.find_events(*args, limit=300, order="magnitude", **kw)]
    batch_ids = sorted(set(summary["batch_ids"]) | {e["batch_id"] for e in nearest if e["batch_id"]})
    return {"summary": summary, "biggest": biggest, "nearest": nearest, "map_points": map_points,
            "batch_ids": batch_ids, "loaded": loaded}


def data_notes(plan: EventPlan) -> list[str]:
    notes = []
    p = plan.place
    if p and plan.region:
        notes.append(f"Searched {plan.region['name']} (records that name it; satellite-tracked events within "
                     f"{plan.radius_km:g} km).")
    elif p:
        notes.append(f"Searched within {plan.radius_km:g} km of {p['label']}.")
    else:
        notes.append("Searched worldwide.")
    if "noaa-storm-events" in plan.sources:
        latest = ev.coverage_note("noaa-storm-events")
        notes.append(f"US storm events are NWS-verified records from the NOAA Storm Events Database, published a few "
                     f"months behind (latest event on file: {latest}).")
    missing = [t for t in plan.types if not any(s in plan.sources for s in ev.TYPE_SOURCES.get(t, []))]
    if missing:
        notes.append(f"No records for {', '.join(TYPE_LABEL[t].lower() for t in missing)} outside the United States "
                     f"(NOAA Storm Events only covers the US).")
    if "nasa-eonet" in plan.sources:
        notes.append("NASA EONET lists notable events tracked by satellite and agencies, not every small one.")
    if "usgs-earthquakes" in plan.sources:
        notes.append("Earthquakes are USGS records of magnitude 2.5 and above since 1990 (5.5 and above before, "
                     "when smaller quakes weren't catalogued worldwide).")
    if "noaa-sig-earthquakes" in plan.sources:
        notes.append("Deaths and damage come from the NOAA NCEI Significant Earthquake Database (about 4,000 "
                     "damaging or deadly earthquakes since 1900).")
    if "ibtracs" in plan.sources:
        notes.append("Tropical cyclones are NOAA IBTrACS best tracks since 1980 (one record per storm; peak "
                     "1-minute winds in knots, categories on the Saffir-Simpson scale). A storm counts for a place if "
                     "its track passed within the search radius." + (f" Basin: {plan.basin_name}." if plan.basin_name else ""))
    if "gdacs" in plan.sources:
        notes.append("Worldwide floods and droughts are GDACS alerts since 2001 (Green, Orange or Red by impact).")
    return notes


def _yearly_trends(plan: EventPlan, by_year: list[dict]) -> dict:
    """Least-squares change per decade over complete years (missing years count as zero events)."""
    import numpy as np
    last = min((plan.end - timedelta(microseconds=1)).year, datetime.now(timezone.utc).year - 1)
    years = list(range(plan.start.year, last + 1))
    if len(years) < 5:
        return {}
    rows = {y["year"]: y for y in by_year}
    xs = np.array(years, float)
    out = {"years": f"{years[0]}-{years[-1]}",
           "count": round(float(np.polyfit(xs, [rows.get(y, {}).get("count", 0) for y in years], 1)[0]) * 10, 2)}
    for key in ("mean_magnitude", "max_magnitude", "mean_lat", "mean_duration_days"):
        pts = [(y, rows[y][key]) for y in years if y in rows and rows[y].get(key) is not None]
        if len(pts) >= 5:
            out[key] = round(float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0]) * 10, 3)
    return out


def _month_bars(plan: EventPlan, by_month: dict) -> list[dict]:
    months, d = [], date(plan.start.year, plan.start.month, 1)
    last = (plan.end - timedelta(microseconds=1)).date()
    while d <= last:
        months.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    if len(months) > 36:  # long spans: by year instead
        years: dict[str, int] = {}
        for m in months:
            years[str(m.year)] = years.get(str(m.year), 0) + by_month.get(m.strftime("%Y-%m"), 0)
        return [{"label": y, "value": n} for y, n in years.items()]
    return [{"label": m.strftime("%b %Y"), "value": by_month.get(m.strftime("%Y-%m"), 0)} for m in months]


def analyze_events(client: genai.Client, model: str, question: str, plan: EventPlan, found: dict, notes: list[str]) -> Analysis:
    payload = {"question": question, "search": plan.to_dict() | {"event_type_names": [TYPE_LABEL[t] for t in plan.types]},
               "totals": {k: found["summary"][k] for k in ("count", "by_type", "deaths", "injuries", "damage_usd")},
               "by_month": found["summary"]["by_month"], "biggest": found["biggest"][:10], "nearest": found["nearest"],
               "data_notes": notes}
    by_year = found["summary"]["by_year"]
    if len(by_year) >= 5:
        payload.pop("by_month")
        payload["by_year"] = by_year
        payload["trends_per_decade"] = _yearly_trends(plan, by_year)

    def generate(feedback: str | None) -> Analysis:
        contents = json.dumps(payload, ensure_ascii=False, default=str) + ("\n\n" + feedback if feedback else "")
        response = client.models.generate_content(
            model=model, contents=contents,
            config=gtypes.GenerateContentConfig(system_instruction=INSTRUCTIONS, response_mime_type="application/json",
                                                response_schema=Analysis, temperature=0.2,
                                                automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True)))
        return response.parsed or Analysis.model_validate_json(response.text)

    return grounded(generate, json.loads(json.dumps(payload, default=str)), question)


def anchor_events(question: str, answer_text: str, plan: EventPlan, found: dict, sources: list[dict], fact: dict) -> dict:
    record = build_record(
        query=question,
        result={"answer": answer_text, "count": found["summary"]["count"], "by_type": found["summary"]["by_type"],
                "search": plan.to_dict(), "events": [e["id"] for e in found["biggest"]],
                "fact_check": {k: fact[k] for k in ("ok", "checked", "unsupported", "evidence_sha256")}},
        source=json.dumps({"batches": [{"batch_id": b["batch_id"], "source": b["source"],
                                        "manifest_sha256": b["manifest_sha256"]} for b in sources]},
                          sort_keys=True, separators=(",", ":")))
    digest = sha256_hex(record)
    solana = get_solana()
    try:
        tx = solana.send_memo(memo_for(digest))
    except SolanaUnavailable as e:
        return {"record": record, "hash": digest, "signature": None, "explorer_url": None, "mode": solana.mode,
                "error": str(e), "badge": {"verified": False, "label": "Not verified"}}
    return {"record": record, "hash": digest, "signature": tx.signature, "explorer_url": tx.explorer_url,
            "mode": solana.mode, "cluster": tx.cluster, "slot": tx.slot,
            "badge": {"verified": True, "label": "Verified on Solana" if solana.mode == "rpc" else "Verified (simulated)"}}


def build_card(client, model: str, question: str, analysis_question: str, plan: EventPlan, provenance_fn, lap) -> dict:
    found = fetch_events(plan)
    lap("fetch")
    notes = data_notes(plan)
    sources, provenance_error = provenance_fn(found["batch_ids"])
    analysis, fact = analyze_events(client, model, analysis_question, plan, found, notes)
    lap("analyze")
    verification = anchor_events(question, analysis.answer_text, plan, found, sources, fact)
    lap("verify")
    p = plan.place
    return {
        "kind": "events",
        "answer_text": analysis.answer_text,
        "trends": analysis.trends,
        "comparison": analysis.comparison,
        "chart": {"type": "bar", "title": analysis.chart.title, "y_label": "Events", "x_label": "",
                  "bars": _month_bars(plan, found["summary"]["by_month"])},
        "events": {"count": found["summary"]["count"], "by_type": found["summary"]["by_type"],
                   "deaths": found["summary"]["deaths"], "injuries": found["summary"]["injuries"],
                   "damage_usd": found["summary"]["damage_usd"], "biggest": found["biggest"], "nearest": found["nearest"]},
        "map": {"center": {"lat": p["lat"], "lon": p["lon"]} if p else None, "radius_km": plan.radius_km,
                "points": [{k: e[k] for k in ("lat", "lon", "type", "name", "date", "strength", "region")}
                           for e in found["map_points"] + found["nearest"] if e["lat"] is not None]},
        "data_notes": notes,
        "provenance": sources,
        **({"provenance_error": provenance_error} if provenance_error else {}),
        "verification": verification,
        "fact_check": fact,
        "grounding": grounding_badge(fact),
    }


# ---------------------------------------------------------------- likelihood ("will there be a tornado near Philly next year?")

LIKELIHOOD_YEARS = 5
LIKELIHOOD_INSTRUCTIONS = """You are Ecuery, answering how LIKELY natural-disaster events are in an upcoming period.
Use ONLY the data provided. This is a statistical estimate from how often such events happened in the same area
and season in recent years; say so, and never present it as a prediction of a specific event. Give the probability
exactly as written in probability_at_least_one (e.g. "more than 99%"), the expected count, and the per-year history it's based on (years with and without events). Round to one decimal place.
Write numbers as digits. 2-4 plain sentences: no markdown or bullets, it will be read aloud.
For the chart, choose a bar chart titled for past event counts per year."""


def probability_text(p: float) -> str:
    """Never round a statistical estimate up to certainty (or down to impossibility)."""
    if p > 0.99:
        return "more than 99%"
    if 0 < p < 0.01:
        return "less than 1%"
    return f"{100 * p:.0f}%"


def _shift(d: datetime, years: int) -> datetime:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # Feb 29
        return d.replace(year=d.year - years, day=28)


def build_likelihood_card(client, model: str, question: str, analysis_question: str, plan: EventPlan,
                          provenance_fn, lap, now: datetime) -> dict:
    import math
    window_days = (plan.end - plan.start).days
    offset = max(1, math.ceil((plan.end - now).days / 365.25))  # shift the window back until it's fully in the past
    base = []
    for k in range(offset, offset + LIKELIHOOD_YEARS):
        base.append((_shift(plan.start, k), _shift(plan.end, k)))
    if plan.sources:
        ev.ensure_events(plan.types, min(s for s, _ in base), max(e for _, e in base), plan.sources)
    p = plan.place
    geo = (p["lat"], p["lon"], plan.radius_km) if p else (None, None, None)
    kw = plan.query_kw()
    per_year, batch_ids = [], set()
    for s, e in base:
        summary = ev.summarize_events(plan.types, s, e, *geo, **kw)
        batch_ids.update(summary["batch_ids"])
        label = str(s.year) if window_days >= 360 else f"{s:%b %d, %Y}"
        per_year.append({"label": label, "value": summary["count"], "start": s.date().isoformat()})
    per_year.sort(key=lambda b: b["start"])
    counts = [b["value"] for b in per_year]
    rate = sum(counts) / len(counts)                      # expected events per window
    probability = 1 - math.exp(-rate)                     # Poisson: chance of at least one
    years_with = sum(1 for c in counts if c > 0)
    lap("fetch")

    notes = data_notes(plan) + [
        f"Likelihood is estimated from the same {window_days}-day window in each of the {LIKELIHOOD_YEARS} most recent "
        f"comparable years ({per_year[0]['label']} to {per_year[-1]['label']}), assuming events occur at the average "
        f"historical rate. It is not a prediction of any specific event."]
    sources, provenance_error = provenance_fn(sorted(batch_ids))
    payload = {"question": question, "today": now.date().isoformat(),
               "upcoming_window": plan.to_dict() | {"event_type_names": [TYPE_LABEL[t] for t in plan.types]},
               "history_per_window": [{"period_starting": b["start"], "count": b["value"]} for b in per_year],
               "expected_count": round(rate, 2), "probability_at_least_one": probability_text(probability),
               "windows_with_events": years_with, "windows_total": len(counts), "data_notes": notes}

    def generate(feedback):
        contents = json.dumps(payload, ensure_ascii=False, default=str) + ("\n\n" + feedback if feedback else "")
        response = client.models.generate_content(
            model=model, contents=contents,
            config=gtypes.GenerateContentConfig(system_instruction=LIKELIHOOD_INSTRUCTIONS, response_mime_type="application/json",
                                                response_schema=Analysis, temperature=0.2,
                                                automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True)))
        return response.parsed or Analysis.model_validate_json(response.text)

    analysis, fact = grounded(generate, payload, question)
    lap("analyze")
    found = {"summary": {"count": sum(counts), "by_type": {}}, "biggest": []}
    verification = anchor_events(question, analysis.answer_text, plan, found, sources, fact)
    lap("verify")
    return {
        "kind": "likelihood",
        "answer_text": analysis.answer_text,
        "trends": analysis.trends,
        "comparison": analysis.comparison,
        "chart": {"type": "bar", "title": analysis.chart.title, "y_label": "Events", "x_label": "",
                  "bars": [{"label": b["label"], "value": b["value"]} for b in per_year]},
        "likelihood": {"probability_pct": min(round(100 * probability, 1), 99.0) if probability < 1 else 99.0,
                       "probability_text": probability_text(probability), "expected_count": round(rate, 2),
                       "windows_with_events": years_with, "windows_total": len(counts), "history": per_year},
        "data_notes": notes,
        "provenance": sources,
        **({"provenance_error": provenance_error} if provenance_error else {}),
        "verification": verification,
        "fact_check": fact,
        "grounding": grounding_badge(fact),
    }
