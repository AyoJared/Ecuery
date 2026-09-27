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

import os
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from google import genai

from parser import EnvironmentalQuery, parse_query
from readings.service import get_readings
from shared.series import DataUnavailable
from tiger.repo import get_repo as get_tiger
from tiger.sample_data import LOCATIONS, METRICS
from verify.hashing import build_record, memo_for, sha256_hex
from verify.solana_client import SolanaUnavailable, get_client as get_solana
from warehouse.repo import get_repo as get_warehouse
from warehouse.sample_data import HISTORY_START

from .analyze import analyze

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
    metrics: list[str]
    locations: list[str]
    start: datetime
    end: datetime
    operation: str

    def to_dict(self) -> dict:
        return asdict(self) | {"start": self.start.isoformat(), "end": self.end.isoformat()}


class NeedsClarification(Exception):
    pass


def _nice(location: str) -> str:
    return location.replace("_", " ").title()


def make_plan(q: EnvironmentalQuery, now: datetime) -> Plan:
    """The diagram's "Read-only & valid?" gate: everything must map onto data we actually have."""
    if not q.metrics:
        raise NeedsClarification(q.clarification_question or
                                 f"Which measurement do you mean? I have {', '.join(METRICS)}.")
    if not q.locations:
        raise NeedsClarification(q.clarification_question or "Which city are you asking about?")
    unknown = [l for l in q.locations if l not in LOCATIONS]
    if unknown:
        have = ", ".join(_nice(l) for l in sorted(LOCATIONS))
        raise NeedsClarification(f"I don't have data for {', '.join(_nice(l) for l in unknown)} yet. "
                                 f"Try one of: {have}.")

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
        start = datetime.combine(max(start_day, HISTORY_START), datetime.min.time(), timezone.utc)
    else:
        start = end - (timedelta(hours=24) if operation == "latest" else timedelta(days=7))
    if start >= end:
        raise NeedsClarification("That time period looks empty or in the future. Which dates do you mean?")

    pairs = [(m, l) for m in dict.fromkeys(q.metrics) for l in dict.fromkeys(q.locations)][:MAX_SERIES]
    return Plan(sorted({m for m, _ in pairs}, key=q.metrics.index), sorted({l for _, l in pairs}, key=q.locations.index),
                start, end, operation)


def _shift_years(t: datetime, years: int) -> datetime:
    try:
        return t.replace(year=t.year - years)
    except ValueError:  # Feb 29
        return t.replace(year=t.year - years, day=28)


def fetch(plan: Plan) -> tuple[list[dict], list[dict]]:
    series = [get_readings(m, l, plan.start, plan.end) for m in plan.metrics for l in plan.locations]
    baselines = []
    if plan.operation == "compare_history":
        for m in plan.metrics:
            for l in plan.locations:
                by_year = []
                for y in range(1, BASELINE_YEARS + 1):
                    s, e = _shift_years(plan.start, y), _shift_years(plan.end, y)
                    if e.date() <= HISTORY_START:
                        break
                    past = get_readings(m, l, max(s, datetime.combine(HISTORY_START, datetime.min.time(), timezone.utc)), e)
                    if past["summary"]:
                        by_year.append({"year": s.year, "avg": past["summary"]["avg"], "max": past["summary"]["max"]})
                if by_year:
                    baselines.append({"metric": m, "location": l, "unit": METRICS[m][0], "by_year": by_year,
                                      "baseline_avg": round(sum(b["avg"] for b in by_year) / len(by_year), 2)})
    return series, baselines


def build_chart(choice, series: list[dict], baselines: list[dict]) -> dict:
    names = {"pm25": "PM2.5", "o3": "Ozone", "no2": "NO2", "co2": "CO2", "temperature": "Temperature", "humidity": "Humidity"}
    label = lambda s: f"{names.get(s['metric'], s['metric'])} · {_nice(s['location'])}"
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


def anchor(question: str, analysis, series: list[dict]) -> dict:
    """Step 8: SHA-256 of query + result + source + timestamp, written to Solana as a memo."""
    stores = sorted({src for s in series for src in s.get("sources", {})})
    modes = {"tiger": get_tiger().mode, "snowflake": get_warehouse().mode}
    record = build_record(
        query=question,
        result={"answer": analysis.answer_text,
                "series": [{k: s[k] for k in ("metric", "location", "route", "sources", "summary")} for s in series]},
        source=", ".join(f"{s}:{modes[s]}" for s in stores) or "none",
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


def ask(question: str, voice: str = "rachel") -> dict:
    timings: dict[str, float] = {}
    t = time.perf_counter()

    def lap(name: str):
        nonlocal t
        now = time.perf_counter()
        timings[name] = round(now - t, 2)
        t = now

    client = get_gemini()
    now = datetime.now(timezone.utc)
    parsed = parse_query(client, question, today=now.date(), model=MODEL)
    lap("understand")
    understood = {k: v for k, v in parsed.model_dump().items()
                  if k in ("intent", "metrics", "locations", "start_date", "end_date", "operation") and v not in (None, [])}

    try:
        plan = make_plan(parsed, now)
    except NeedsClarification as e:
        return {"status": "needs_clarification", "question": question, "clarification": str(e),
                "understood": understood, "timings": timings}

    series, baselines = fetch(plan)
    lap("fetch")
    analysis = analyze(client, MODEL, question, plan.to_dict(), series, baselines)
    lap("analyze")
    verification = anchor(question, analysis, series)
    lap("verify")

    return {
        "status": "answered",
        "question": question,
        "understood": understood,
        "plan": plan.to_dict(),
        "answer_text": analysis.answer_text,
        "trends": analysis.trends,
        "comparison": analysis.comparison,
        "chart": build_chart(analysis.chart, series, baselines),
        "data": [{k: s[k] for k in ("metric", "location", "unit", "route", "granularity", "sources", "warnings", "summary")}
                 for s in series],
        "historical_baselines": baselines,
        "audio_url": "/voice/speak?" + urlencode({"text": analysis.answer_text, "voice": voice}),
        "verification": verification,
        "timings": timings,
    }
