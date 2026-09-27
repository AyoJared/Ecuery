"""Step 4 API: historical environmental data from Snowflake.

GET  /warehouse/status     live Snowflake or mock, plus date coverage
GET  /warehouse/metrics
GET  /warehouse/locations
GET  /warehouse/history    ?metric=pm25&location=new_york&years=5&granularity=auto
POST /warehouse/sql        {sql, limit} -> read-only query (Gemini-generated SQL)
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from shared.series import DataUnavailable, error_text, parse_time
from shared.sql_guard import UnsafeSQL

from .repo import SCHEMA_DESCRIPTION, WarehouseRepo, get_repo

router = APIRouter(prefix="/warehouse", tags=["warehouse"])


class SQLRequest(BaseModel):
    sql: str
    limit: int = Field(200, ge=1, le=1000)


def _db(fn, *args):
    try:
        return fn(*args)
    except DataUnavailable as e:
        raise HTTPException(503, str(e))


@router.get("/status")
def status(repo: WarehouseRepo = Depends(get_repo)):
    return {"mode": repo.mode, "coverage": _db(repo.coverage), "schema": SCHEMA_DESCRIPTION}


@router.get("/metrics")
def metrics(repo: WarehouseRepo = Depends(get_repo)):
    return _db(repo.list_metrics)


@router.get("/locations")
def locations(repo: WarehouseRepo = Depends(get_repo)):
    return _db(repo.list_locations)


@router.get("/history")
def history(
    metric: str,
    location: str,
    years: float = Query(5, gt=0, le=30),
    start: str | None = Query(None, description="ISO date/time, overrides years"),
    end: str | None = Query(None, description="ISO date/time, defaults to now"),
    granularity: str = Query("auto", pattern="^(auto|daily|monthly|yearly)$"),
    repo: WarehouseRepo = Depends(get_repo),
):
    try:
        end_dt = parse_time(end) if end else datetime.now(timezone.utc)
        start_dt = parse_time(start) if start else end_dt - timedelta(days=365.25 * years)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if start_dt >= end_dt:
        raise HTTPException(400, "start must be before end")
    return _db(repo.history, metric.lower(), location.lower(), start_dt, end_dt, granularity)


@router.post("/sql")
def run_sql(req: SQLRequest, repo: WarehouseRepo = Depends(get_repo)):
    try:
        return repo.run_readonly_sql(req.sql, req.limit)
    except UnsafeSQL as e:
        raise HTTPException(400, f"Rejected: {e}")
    except DataUnavailable as e:
        raise HTTPException(503, str(e))
    except Exception as e:  # invalid SQL, timeout, permission denied for the reader role
        raise HTTPException(400, f"Query failed: {error_text(e)}")
