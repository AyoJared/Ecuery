"""Diagram: "Route by time range" -> Tiger / Snowflake -> "Merge on time + location".

Tiger holds the last RECENT_DAYS days; Snowflake holds everything older.
get_readings() sends each part of the requested window to the right store and
stitches the points into one series, tagging each point with where it came
from. compare_to_history() is the "compare recent vs historical" input for
Gemini's analysis step.
"""

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from shared.series import DataUnavailable, make_point, make_result
from tiger.repo import get_repo as get_tiger
from tiger.sample_data import METRICS
from warehouse.repo import get_repo as get_warehouse

RECENT_DAYS = int(os.getenv("RECENT_DAYS", "14"))


def recent_cutoff(now: datetime | None = None) -> datetime:
    """Start of the recent window, at midnight UTC so daily buckets never straddle two stores."""
    now = now or datetime.now(timezone.utc)
    day = (now - timedelta(days=RECENT_DAYS)).date()
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _tag(points: list[dict], source: str) -> list[dict]:
    return [{**p, "source": source} for p in points]


def _to_monthly(points: list[dict]) -> list[dict]:
    months: dict[str, list[dict]] = defaultdict(list)
    for p in points:
        months[p["time"][:7]].append(p)
    out = []
    for key, ps in sorted(months.items()):
        weight = sum(p["samples"] for p in ps) or 1
        avg = sum(p["avg"] * p["samples"] for p in ps) / weight
        out.append(make_point(datetime.fromisoformat(key + "-01"), avg, min(p["min"] for p in ps),
                              max(p["max"] for p in ps), sum(p["samples"] for p in ps),
                              "+".join(sorted({p["source"] for p in ps}))))
    return out


def get_readings(metric: str, location: str, start: datetime, end: datetime) -> dict:
    metric, location = metric.lower(), location.lower()
    cutoff = recent_cutoff()
    route = "recent" if start >= cutoff else "historical" if end <= cutoff else "both"
    warnings: list[str] = []
    points: list[dict] = []
    sources: dict[str, int] = {}

    def fetch(name: str, fn, *args) -> dict | None:
        try:
            result = fn(*args)
        except DataUnavailable as e:
            warnings.append(f"{name}: {e}")
            return None
        sources[name] = result["count"]
        return result

    if route == "recent":
        r = fetch("tiger", get_tiger().recent, metric, location, start, end, "auto")
        granularity = r["granularity"] if r else "auto"
        points = _tag(r["points"], "tiger") if r else []
    elif route == "historical":
        r = fetch("snowflake", get_warehouse().history, metric, location, start, end, "auto")
        granularity = r["granularity"] if r else "auto"
        points = _tag(r["points"], "snowflake") if r else []
    else:
        # Both stores have daily data, so merge at daily grain (monthly for long spans).
        old = fetch("snowflake", get_warehouse().history, metric, location, start, cutoff, "daily")
        new = fetch("tiger", get_tiger().recent, metric, location, cutoff, end, "daily")
        merged = {p["time"]: p for p in _tag(old["points"], "snowflake")} if old else {}
        merged.update({p["time"]: p for p in _tag(new["points"], "tiger")} if new else {})  # Tiger wins on overlap
        points = [merged[k] for k in sorted(merged)]
        granularity = "daily"
        if end - start > timedelta(days=400):
            points, granularity = _to_monthly(points), "monthly"

    if not sources:
        raise DataUnavailable("; ".join(warnings) or "No data source available")
    return make_result(metric, location, METRICS.get(metric, ("",))[0], granularity, start, end, points,
                       route=route, recent_cutoff=cutoff.isoformat(), sources=sources, warnings=warnings)


def _years_back(t: datetime, years: int) -> datetime:
    try:
        return t.replace(year=t.year - years)
    except ValueError:  # Feb 29
        return t.replace(year=t.year - years, day=28)


def compare_to_history(metric: str, location: str, days: int = 7, years: int = 5) -> dict:
    """Last `days` days (Tiger) vs the same calendar window in each of the previous `years` years (Snowflake)."""
    metric, location = metric.lower(), location.lower()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    recent = get_tiger().recent(metric, location, start, end, "daily")
    if not recent["summary"]:
        raise DataUnavailable(f"No recent {metric} data for {location}")

    warehouse = get_warehouse()
    past = []
    for y in range(1, years + 1):
        r = warehouse.history(metric, location, _years_back(start, y), _years_back(end, y), "daily")
        if r["summary"]:
            past.append({"year": _years_back(end, y).year, **{k: r["summary"][k] for k in ("avg", "min", "max")}})
    if not past:
        raise DataUnavailable(f"No historical {metric} data for {location} in that window")

    recent_avg = recent["summary"]["avg"]
    baseline = round(sum(p["avg"] for p in past) / len(past), 2)
    change = round((recent_avg - baseline) / baseline * 100, 1) if baseline else None
    return {
        "metric": metric,
        "location": location,
        "unit": recent["unit"],
        "window_days": days,
        "recent": {"start": start.isoformat(), "end": end.isoformat(), **{k: recent["summary"][k] for k in ("avg", "min", "max")}},
        "historical_baseline_avg": baseline,
        "change_pct": change,
        "direction": "higher" if change and change > 0 else "lower" if change and change < 0 else "about the same",
        "by_year": past,
        "sources": {"recent": get_tiger().mode, "historical": warehouse.mode},
    }

