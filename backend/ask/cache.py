"""Query cache (the "Redis: cache common queries" row of the stack).

Three layers, each keyed on what actually determines the result, so relative dates
("last 3 days") and follow-ups ("what about Philadelphia?") never get a stale answer:

  understand  question wording + today's date + previous turn  -> Gemini's parsed query
  data        resolved plan (metrics, locations, exact window)  -> Tiger/Snowflake series
  answer      question wording + resolved plan                  -> analysis, chart and its Solana proof

Historical windows never change, so they're kept 24h; windows reaching up to "now" 5 minutes.
Redis when REDIS_URL is set, else in-process. A cache failure is treated as a miss, never an error.
"""

import hashlib
import json
import logging
import re
import threading
import time
from typing import Any, Protocol

from .memory import redis_client

PREFIX = "ecuery:cache:"
TTL_HISTORICAL = 24 * 60 * 60
TTL_RECENT = 5 * 60
TTL_UNDERSTAND = 60 * 60

log = logging.getLogger(__name__)


class Cache(Protocol):
    mode: str

    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, ttl: int) -> None: ...

    def clear(self) -> int: ...


class InMemoryCache:
    mode = "memory"
    MAX_ENTRIES = 500

    def __init__(self):
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if not entry or entry[0] < time.time():
                self._data.pop(key, None)
                return None
            return json.loads(entry[1])

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            if len(self._data) >= self.MAX_ENTRIES:
                self._data.pop(min(self._data, key=lambda k: self._data[k][0]))
            self._data[key] = (time.time() + ttl, json.dumps(value, ensure_ascii=False))

    def clear(self) -> int:
        with self._lock:
            n = len(self._data)
            self._data.clear()
            return n


class RedisCache:
    mode = "redis"

    def __init__(self, client):
        self.r = client

    def get(self, key: str) -> Any | None:
        try:
            raw = self.r.get(key)
        except Exception as e:  # cache trouble must never break an answer
            log.warning("cache get failed: %s", e)
            return None
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            self.r.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except Exception as e:
            log.warning("cache set failed: %s", e)

    def clear(self) -> int:
        keys = list(self.r.scan_iter(match=PREFIX + "*", count=500))
        return self.r.delete(*keys) if keys else 0


def normalize(question: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.]", " ", question.lower())).strip()


def cache_key(kind: str, parts: dict) -> str:
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]
    return f"{PREFIX}{kind}:{digest}"


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        client = redis_client()
        _cache = RedisCache(client) if client else InMemoryCache()
    return _cache
