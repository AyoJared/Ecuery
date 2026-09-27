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

US_ONLY = {"noaa-storm-events"}
TYPE_LABEL = ev.EVENT_TYPES

INSTRUCTIONS = """You are Ecuery, an environmental data assistant answering a question about natural disasters or
weather events. Use ONLY the data provided: exact counts, totals and the listed events. Never invent events or numbers.
Lead with the direct answer (e.g. "No tornadoes touched down in Philadelphia in 2025."). If the count is zero or small,
mention the nearest events outside the search area from "nearest", with distance, date, strength and place.
Name the strongest or most damaging events with dates. Give tornado ratings as EF0-EF5 and earthquake magnitudes as M.
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

    def to_dict(self) -> dict:
        return {"event_types": self.types, "start": self.start.isoformat(), "end": self.end.isoformat(),
                "operation": self.operation, "place": self.place and {k: self.place[k] for k in ("key", "label", "lat", "lon")},
                "radius_km": self.radius_km, "min_magnitude": self.min_magnitude, "sources": self.sources,
                "within": self.region and self.region["name"]}


def make_event_plan(q, now: datetime) -> EventPlan:
    types = list(dict.fromkeys(q.event_types))
    names = [l for l in dict.fromkeys(q.locations) if places.slug(l) != places.GLOBAL]
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
    end = now if end_day is None or end_day >= now.date() else datetime.combine(end_day + timedelta(days=1), datetime.min.time(), timezone.utc)
    start = datetime.combine(start_day, datetime.min.time(), timezone.utc) if start_day else end - timedelta(days=365)
    if start >= end:
        raise NeedsClarification("That time period looks empty or in the future. Which dates do you mean?")

    sources = sorted({s for t in types for s in ev.TYPE_SOURCES.get(t, [])})
    if place and (place.country_code or "").upper() != "US":
        sources = [s for s in sources if s not in US_ONLY]
    radius = (q.radius_km or ev.default_radius(types, place.radius_km)) if place else None
    region = None
    if place and not q.radius_km and place.feature_code in ("state", "province", "region") and place.country_code == "US":
        region = {"name": place.name, "pattern": f"%, {place.name}", "sources": ["noaa-storm-events"]}
    elif place and not q.radius_km and place.feature_code == "country" and place.country_code != "US":
        region = {"name": place.name, "pattern": f"%{place.name}%", "sources": ["usgs-earthquakes"]}
    return EventPlan(types, start, end, q.operation or "count", place.to_dict() if place else None,
                     round(radius, 1) if radius else None, q.min_magnitude, sources, region)


def _event_view(r: dict) -> dict:
    details = r["details"] or {}
    return {"id": f"{r['source']}:{r['event_id']}", "type": r["type"], "name": r["name"],
            "date": r["starts_at"].date().isoformat(), "strength": r["magnitude_label"], "magnitude": r["magnitude"],
            "region": r["region"], "distance_km": round(r["distance_km"], 1) if r.get("distance_km") is not None else None,
            "deaths": r["deaths"], "injuries": r["injuries"], "damage_usd": r["damage_usd"],
            "path_miles": float(details["TOR_LENGTH"]) if details.get("TOR_LENGTH") else None,
            "lat": r["lat"], "lon": r["lon"], "source": r["source"], "batch_id": r["batch_id"]}


def fetch_events(plan: EventPlan) -> dict:
    loaded = ev.ensure_events(plan.types, plan.start, plan.end) if plan.sources else {}
    p = plan.place
    geo = (p["lat"], p["lon"], plan.radius_km) if p else (None, None, None)
    args = (plan.types, plan.start, plan.end, *geo)
    kw = {"min_magnitude": plan.min_magnitude, "sources": plan.sources or ["none"], "region": plan.region}
    summary = ev.summarize_events(*args, **kw)
    biggest = [_event_view(r) for r in ev.find_events(*args, limit=15, order="magnitude", **kw)]
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
        notes.append("Earthquakes are USGS records of magnitude 2.5 and above.")
    return notes


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
    response = client.models.generate_content(
        model=model, contents=json.dumps(payload, ensure_ascii=False, default=str),
        config=gtypes.GenerateContentConfig(system_instruction=INSTRUCTIONS, response_mime_type="application/json",
                                            response_schema=Analysis, temperature=0.2,
                                            automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True)))
    return response.parsed or Analysis.model_validate_json(response.text)


def anchor_events(question: str, answer_text: str, plan: EventPlan, found: dict, sources: list[dict]) -> dict:
    record = build_record(
        query=question,
        result={"answer": answer_text, "count": found["summary"]["count"], "by_type": found["summary"]["by_type"],
                "search": plan.to_dict(), "events": [e["id"] for e in found["biggest"]]},
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
    analysis = analyze_events(client, model, analysis_question, plan, found, notes)
    lap("analyze")
    verification = anchor_events(question, analysis.answer_text, plan, found, sources)
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
    }
