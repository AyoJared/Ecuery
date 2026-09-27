"""Merged readings: routes by time range across Tiger (recent) and Snowflake (history).

GET /readings           ?metric=pm25&location=new_york&start=2023-06-01&end=2023-06-15
                        or ?metric=pm25&location=new_york&days=365
GET /readings/compare   ?metric=pm25&location=philadelphia&days=7&years=5
GET /readings/sources   which stores are live and where the recent/historical split is
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from shared.series import DataUnavailable, parse_time
from tiger.repo import get_repo as get_tiger
from warehouse.repo import get_repo as get_warehouse

from .service import RECENT_DAYS, compare_to_history, get_readings, recent_cutoff

router = APIRouter(prefix="/readings", tags=["readings"])


@router.get("")
def readings(
    metric: str,
    location: str,
    days: float = Query(30, gt=0, le=365 * 30),
    start: str | None = Query(None, description="ISO date/time, overrides days"),
    end: str | None = Query(None, description="ISO date/time, defaults to now"),
):
    try:
        end_dt = parse_time(end) if end else datetime.now(timezone.utc)
        start_dt = parse_time(start) if start else end_dt - timedelta(days=days)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if start_dt >= end_dt:
        raise HTTPException(400, "start must be before end")
    try:
        return get_readings(metric, location, start_dt, end_dt)
    except DataUnavailable as e:
        raise HTTPException(503, str(e))


@router.get("/compare")
def compare(metric: str, location: str, days: int = Query(7, ge=1, le=RECENT_DAYS),
            years: int = Query(5, ge=1, le=20)):
    try:
        return compare_to_history(metric, location, days, years)
    except DataUnavailable as e:
        raise HTTPException(503, str(e))


@router.get("/sources")
def sources():
    return {
        "recent": {"store": "tiger", "mode": get_tiger().mode, "from": recent_cutoff().isoformat()},
        "historical": {"store": "snowflake", "mode": get_warehouse().mode, "until": recent_cutoff().isoformat()},
        "recent_days": RECENT_DAYS,
    }
