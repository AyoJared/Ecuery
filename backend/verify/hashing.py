"""Step 8a/8b: bundle (query + result + source + timestamp) and SHA-256 it.

The hash must be reproducible byte-for-byte, so the record is serialized as
canonical JSON (sorted keys, no whitespace) before hashing. Anyone holding the
same four fields can recompute the hash and compare it to the on-chain memo.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

MEMO_PREFIX = "ecuery:v1:"


def build_record(query: str, result: Any, source: str, timestamp: str | None = None) -> dict:
    return {
        "query": query,
        "result": result,
        "source": source,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def canonical_json(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha256_hex(record: dict) -> str:
    return hashlib.sha256(canonical_json(record)).hexdigest()


def memo_for(digest: str) -> str:
    return f"{MEMO_PREFIX}{digest}"


def digest_from_memo(memo: str) -> str | None:
    return memo[len(MEMO_PREFIX):] if memo.startswith(MEMO_PREFIX) else None
