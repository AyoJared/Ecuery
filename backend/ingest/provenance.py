"""Source provenance: prove where every number came from.

Each ingest run of one source is a Batch. While it runs, every HTTP response from the
agency is fingerprinted (URL + SHA-256 of the raw bytes). When it finishes:

  rows_sha256      hash of the normalized rows we loaded (recomputable from the database)
  manifest_sha256  hash of {source, dataset, quality, fetched_at, requests, rows_sha256, row_count}
  Solana memo      "ecuery:src:v1:<manifest_sha256>", signed by the backend wallet

So anyone can check that (a) the rows in Tiger/Snowflake are exactly what was ingested,
(b) the manifest hasn't been edited since it was anchored, and (c) re-downloading the
listed URLs gives the same bytes (or see that the agency has revised them since).
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import httpx

from verify.solana_client import SolanaUnavailable, get_client as get_solana

USER_AGENT = "Ecuery environmental data (OwlHacks 2026; contact jaredwerts2006@gmail.com)"
MEMO_PREFIX = "ecuery:src:v1:"

_http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True)


def row_line(row: tuple) -> str:
    """Canonical text for one row, identical at ingest and when re-verifying from the database."""
    out = []
    for v in row:
        if isinstance(v, datetime):
            out.append(v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        elif isinstance(v, date):
            out.append(v.isoformat())
        elif isinstance(v, float):
            out.append(f"{v:.4f}")
        else:
            out.append(str(v))
    return "|".join(out)


def rows_sha256(rows: list[tuple]) -> str:
    return hashlib.sha256("\n".join(sorted(row_line(r) for r in rows)).encode()).hexdigest()


def _backoff(resp: httpx.Response, attempt: int) -> float:
    """Server errors: a short pause. Rate limits: honour Retry-After, else wait out a per-minute window
    (Open-Meteo counts a multi-point, multi-year request as many calls)."""
    if resp.status_code != 429:
        return 2 * (attempt + 1)
    try:
        return min(90.0, float(resp.headers.get("Retry-After", "")))
    except ValueError:
        return 20.0 * (attempt + 1)


@dataclass
class Batch:
    source: str          # e.g. "epa-aqs"
    dataset: str         # human description of what was pulled
    quality: str         # "quality-assured" or "preliminary"
    store: str           # "tiger" (recent) or "snowflake" (history)
    batch_id: str = field(default_factory=lambda: f"b_{uuid.uuid4().hex[:16]}")
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    requests: list[dict] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)

    def fetch(self, url: str, params: dict | None = None, retries: int = 4) -> bytes:
        """GET from the agency and fingerprint the exact bytes received."""
        for attempt in range(retries):
            try:
                resp = _http.get(url, params=params)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    time.sleep(_backoff(resp, attempt))
                    continue
                resp.raise_for_status()
                break
            except httpx.TransportError:
                if attempt == retries - 1:
                    raise
                time.sleep(2 * (attempt + 1))
        body = resp.content
        self.requests.append({"url": str(resp.url), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})
        return body

    def manifest(self) -> dict:
        return {
            "source": self.source, "dataset": self.dataset, "quality": self.quality, "store": self.store,
            "batch_id": self.batch_id, "fetched_at": self.fetched_at, "requests": self.requests,
            "row_count": len(self.rows), "rows_sha256": rows_sha256(self.rows),
        }


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def anchor(manifest: dict) -> dict:
    """Write the manifest hash to Solana. Returns signature info (or the error, never raises)."""
    digest = manifest_sha256(manifest)
    solana = get_solana()
    try:
        tx = solana.send_memo(MEMO_PREFIX + digest)
        return {"manifest_sha256": digest, "signature": tx.signature, "explorer_url": tx.explorer_url,
                "cluster": tx.cluster, "chain_mode": solana.mode}
    except SolanaUnavailable as e:
        return {"manifest_sha256": digest, "signature": None, "explorer_url": None,
                "cluster": solana.cluster, "chain_mode": solana.mode, "error": str(e)}
