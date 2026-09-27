"""Forecast answers, plus the forecast track record.

Every forecast answer is anchored on Solana like any other answer: the record commits to the
forecast values and to fingerprints of the model responses they came from. Daily forecast values
are also saved (Tiger table `forecasts`), so once the real data arrives each forecast can be
scored: GET /verify/forecasts reports error and how often reality fell inside the band.
"""

import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from google.genai import types as gtypes

from ingest.store import tiger_conn
from shared.catalog import label as metric_label
from verify.hashing import build_record, memo_for, sha256_hex
from verify.solana_client import SolanaUnavailable, get_client as get_solana

from .analyze import Analysis
from .factcheck import grounded, grounding_badge
from .forecast import ForecastPlan, SourceLog, data_notes, forecast_series, granularity_for, recent_context

INSTRUCTIONS = """You are Ecuery, an environmental data assistant answering a question about the FUTURE.
Use ONLY the forecast data provided. Never invent numbers. State clearly what kind of estimate each part is,
using its method label: a model forecast ("the ECMWF ensemble forecasts ..."), typical conditions ("in past years
these dates averaged ... ; this is what's normal, not a forecast"), a climate projection, or a trend projection.
Always give the uncertainty range (lo-hi) when one is provided, and never present a forecast as certain.
Write numbers as digits. Round to one decimal place. For PM2.5, daily values above 35 µg/m³ are unhealthy for sensitive groups and above 55 are unhealthy for everyone; say so when a forecast reaches them.
2-4 plain sentences: no markdown or bullets, it will be read aloud.
For the chart, choose a line chart titled for the forecast."""

SCHEMA = """CREATE TABLE IF NOT EXISTS forecasts (
    answer_hash TEXT NOT NULL, made_at TIMESTAMPTZ NOT NULL, metric TEXT NOT NULL, location TEXT NOT NULL,
    target_date DATE NOT NULL, value DOUBLE PRECISION NOT NULL, lo DOUBLE PRECISION, hi DOUBLE PRECISION,
    method TEXT NOT NULL, signature TEXT,
    PRIMARY KEY (answer_hash, metric, location, target_date))"""


def _sample(points: list[dict], limit: int = 40) -> list[dict]:
    step = max(1, len(points) // limit)
    picked = points[::step]
    if points and picked[-1] is not points[-1]:
        picked.append(points[-1])
    return [{k: p.get(k) for k in ("time", "value", "lo", "hi", "method")} for p in picked]


def build_forecast_card(client, model: str, question: str, analysis_question: str, plan: ForecastPlan,
                        provenance_fn, lap, now: datetime) -> dict:
    from ingest.on_demand import ensure
    from shared import places

    today = now.date()
    for key, info in plan.places.items():  # new places need history for "typical conditions"
        if info["kind"] == "modeled":
            ensure(places.get(key), [m for m, l in plan.pairs if l == key])
    log = SourceLog()
    series = [forecast_series(m, l, plan, today, log) for m, l in plan.pairs]
    near_term = granularity_for(plan) == "daily" and (plan.start.date() - today).days <= 14
    context = {(s["metric"], s["location"]): recent_context(s["metric"], s["location"], today) if near_term else []
               for s in series}
    lap("forecast")

    notes = data_notes(plan, series)
    history_batches = sorted({b for s in series for b in s["history_batches"]})
    sources, provenance_error = provenance_fn(history_batches)
    label = lambda s: f"{metric_label(s['metric'])} · {plan.places.get(s['location'], {}).get('label', s['location'])}"
    payload = {
        "question": question, "today": today.isoformat(), "forecast_window": plan.to_dict(),
        "series": [{"name": label(s), "unit": s["unit"], "granularity": s["granularity"],
                    "method_labels": s["method_labels"], "summary": s["summary"], "points": _sample(s["points"]),
                    "recent_observed": context[(s["metric"], s["location"])][-3:]} for s in series],
        "data_notes": notes,
    }

    def generate(feedback):
        contents = json.dumps(payload, ensure_ascii=False) + ("\n\n" + feedback if feedback else "")
        response = client.models.generate_content(
            model=model, contents=contents,
            config=gtypes.GenerateContentConfig(system_instruction=INSTRUCTIONS, response_mime_type="application/json",
                                                response_schema=Analysis, temperature=0.2,
                                                automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True)))
        return response.parsed or Analysis.model_validate_json(response.text)

    analysis, fact = grounded(generate, payload, question)
    lap("analyze")
    verification = _anchor(question, analysis.answer_text, plan, series, log.entries, sources, fact)
    lap("verify")
    _store(verification, series, now)

    chart_series = []
    for s in series:
        observed = [{"time": p["time"], "value": p["value"], "forecast": False, "source": "observed"}
                    for p in context[(s["metric"], s["location"])]]
        chart_series.append({"name": label(s), "unit": s["unit"], "granularity": s["granularity"],
                             "points": observed + [{k: p.get(k) for k in ("time", "value", "lo", "hi", "method", "forecast")}
                                                   for p in s["points"]]})
    return {
        "kind": "forecast",
        "answer_text": analysis.answer_text,
        "trends": analysis.trends,
        "comparison": analysis.comparison,
        "chart": {"type": "line", "title": analysis.chart.title, "y_label": analysis.chart.y_label, "x_label": "Time",
                  "series": chart_series},
        "data": [{k: s[k] for k in ("metric", "location", "unit", "granularity", "summary", "methods", "method_labels")}
                 | {"warnings": [], "route": "forecast"} for s in series],
        "data_notes": notes,
        "provenance": sources,
        "forecast_sources": log.entries,
        **({"provenance_error": provenance_error} if provenance_error else {}),
        "verification": verification,
        "fact_check": fact,
        "grounding": grounding_badge(fact),
    }


def _anchor(question, answer_text, plan, series, model_sources, history_sources, fact) -> dict:
    record = build_record(
        query=question,
        result={"answer": answer_text, "forecast": plan.to_dict(),
                "series": [{"metric": s["metric"], "location": s["location"], "methods": s["methods"],
                            "points": [[p["time"][:10], p["value"], p["lo"], p["hi"]] for p in s["points"]]} for s in series],
                "fact_check": {k: fact[k] for k in ("ok", "checked", "unsupported", "evidence_sha256")}},
        source=json.dumps({"models": [{k: e[k] for k in ("source", "url", "sha256")} for e in model_sources],
                           "batches": [{"batch_id": b["batch_id"], "source": b["source"],
                                        "manifest_sha256": b["manifest_sha256"]} for b in history_sources]},
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


def _store(verification: dict, series: list[dict], now: datetime) -> None:
    rows = [(verification["hash"], now, s["metric"], s["location"], date.fromisoformat(p["time"][:10]), p["value"],
             p["lo"], p["hi"], p["method"], verification.get("signature"))
            for s in series if s["granularity"] == "daily" for p in s["points"]]
    if not rows:
        return
    try:
        with tiger_conn() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.executemany("""INSERT INTO forecasts VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT DO NOTHING""", rows)
    except Exception:  # the track record must never break an answer
        pass


def scorecard(limit_days: int = 365) -> dict:
    """Forecast vs what happened, for every stored forecast day that has observations now."""
    from readings.service import get_readings

    today = datetime.now(timezone.utc).date()
    with tiger_conn() as conn:
        conn.execute(SCHEMA)
        rows = conn.execute("""SELECT metric, location, target_date, value, lo, hi, method, answer_hash, signature
                               FROM forecasts WHERE target_date < %s AND target_date >= %s""",
                            (today - timedelta(days=1), today - timedelta(days=limit_days))).fetchall()
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r[0], r[1])].append(r)
    scored = []
    for (metric, location), items in groups.items():
        first, last = min(r[2] for r in items), max(r[2] for r in items)
        as_dt = lambda d: datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        try:
            obs = get_readings(metric, location, as_dt(first), as_dt(last + timedelta(days=1)))
        except Exception:
            continue
        daily: dict[str, list[float]] = defaultdict(list)
        for p in obs["points"]:
            daily[p["time"][:10]].append(p["avg"])
        for r in items:
            actual = daily.get(r[2].isoformat())
            if actual:
                a = statistics.fmean(actual)
                scored.append({"metric": metric, "location": location, "date": r[2].isoformat(), "method": r[6],
                               "forecast": r[3], "actual": round(a, 2), "error": round(r[3] - a, 2),
                               "inside_band": (r[4] <= a <= r[5]) if r[4] is not None and r[5] is not None else None,
                               "answer_hash": r[7], "signature": r[8]})
    by_method: dict[str, list] = defaultdict(list)
    for s in scored:
        by_method[s["method"]].append(s)
    summary = {}
    for method, items in by_method.items():
        banded = [s for s in items if s["inside_band"] is not None]
        summary[method] = {"days_scored": len(items),
                           "mean_abs_error": round(statistics.fmean(abs(s["error"]) for s in items), 2),
                           "inside_band_pct": round(100 * sum(s["inside_band"] for s in banded) / len(banded), 1) if banded else None}
    return {"scored_days": len(scored), "by_method": summary, "pending_days": len(rows) - len(scored),
            "recent": sorted(scored, key=lambda s: s["date"], reverse=True)[:50]}
