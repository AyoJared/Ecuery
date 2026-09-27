"""The time-series shape every data source returns (Tiger, Snowflake, merged).

Keeping one shape means the frontend chart, Gemini and the merge step never
care where a point came from.
"""

from datetime import date, datetime, timezone
from typing import Any


class DataUnavailable(RuntimeError):
    """A data source can't be reached or isn't configured."""


def error_text(e: Exception, limit: int = 400) -> str:
    """Full error message on one line (Snowflake puts the useful part after the first line)."""
    return " ".join(str(e).split())[:limit]


def parse_time(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def as_utc(t: date | datetime) -> datetime:
    if isinstance(t, datetime):
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return datetime(t.year, t.month, t.day, tzinfo=timezone.utc)


def make_point(time: date | datetime, avg: float, lo: float, hi: float, samples: int, source: str | None = None) -> dict:
    point = {"time": as_utc(time).isoformat(), "avg": round(avg, 2), "min": round(lo, 2),
             "max": round(hi, 2), "samples": int(samples)}
    if source:
        point["source"] = source
    return point


def summarize(points: list[dict]) -> dict | None:
    if not points:
        return None
    return {
        "avg": round(sum(p["avg"] for p in points) / len(points), 2),
        "min": round(min(p["min"] for p in points), 2),
        "max": round(max(p["max"] for p in points), 2),
        "latest": points[-1]["avg"],
        "latest_time": points[-1]["time"],
    }


def make_result(metric: str, location: str, unit: str, granularity: str,
                start: datetime, end: datetime, points: list[dict], **extra: Any) -> dict:
    return {
        "metric": metric,
        "location": location,
        "unit": unit,
        "granularity": granularity,
        "start": start.isoformat(),
        "end": end.isoformat(),
        **extra,
        "count": len(points),
        "summary": summarize(points),
        "points": points,
    }


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)
