"""Step 3 API: recent environmental data from Tiger Data.

GET  /tiger/status     live Tiger service or mock
GET  /tiger/metrics    metrics + units available
GET  /tiger/locations  locations available
GET  /tiger/recent     ?metric=pm25&location=philadelphia&hours=24&granularity=auto
POST /tiger/sql        {sql, limit} -> read-only query (Gemini-generated SQL)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .repo import MAX_HOURS, SCHEMA_DESCRIPTION, TigerUnavailable, TigerRepo, get_repo, resolve_window
from shared.sql_guard import UnsafeSQL

router = APIRouter(prefix="/tiger", tags=["tiger"])


class SQLRequest(BaseModel):
    sql: str
    limit: int = Field(200, ge=1, le=1000)


@router.get("/status")
def status(repo: TigerRepo = Depends(get_repo)):
    return {"mode": repo.mode, "schema": SCHEMA_DESCRIPTION}


def _db(fn, *args):
    try:
        return fn(*args)
    except TigerUnavailable as e:
        raise HTTPException(503, str(e))


@router.get("/metrics")
def metrics(repo: TigerRepo = Depends(get_repo)):
    return _db(repo.list_metrics)


@router.get("/locations")
def locations(repo: TigerRepo = Depends(get_repo)):
    return _db(repo.list_locations)


@router.get("/recent")
def recent(
    metric: str,
    location: str,
    hours: float = Query(24, gt=0, le=MAX_HOURS),
    start: str | None = Query(None, description="ISO time, overrides hours"),
    end: str | None = Query(None, description="ISO time, defaults to now"),
    granularity: str = Query("auto", pattern="^(auto|raw|hourly|daily)$"),
    repo: TigerRepo = Depends(get_repo),
):
    try:
        start_dt, end_dt = resolve_window(hours, start, end)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _db(repo.recent, metric.lower(), location.lower(), start_dt, end_dt, granularity)


@router.post("/sql")
def run_sql(req: SQLRequest, repo: TigerRepo = Depends(get_repo)):
    try:
        return repo.run_readonly_sql(req.sql, req.limit)
    except UnsafeSQL as e:
        raise HTTPException(400, f"Rejected: {e}")
    except TigerUnavailable as e:
        raise HTTPException(503, str(e))
    except Exception as e:  # invalid SQL, timeout, read-only violation from Postgres
        raise HTTPException(400, f"Query failed: {e}")
