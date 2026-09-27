"""Conversation memory, so follow-ups like "what about Philadelphia?" or "is that normal?" work.

Each conversation keeps its last MAX_TURNS turns: the question, what Gemini understood
(metric / location / time range / operation) and a short answer. RedisStore is used
when REDIS_URL is set, so memory survives restarts and is shared across workers;
otherwise InMemoryStore keeps it in this process (lost on restart / --reload).
"""

import json
import os
import threading
import time
import uuid
from typing import Protocol

MAX_TURNS = 6
TTL_SECONDS = 2 * 60 * 60  # forget a conversation after 2 hours of silence


class MemoryStore(Protocol):
    mode: str

    def history(self, conversation_id: str) -> list[dict]: ...

    def append(self, conversation_id: str, turn: dict) -> None: ...

    def clear(self, conversation_id: str) -> None: ...


class InMemoryStore:
    mode = "memory"

    def __init__(self):
        self._data: dict[str, tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()

    def history(self, conversation_id: str) -> list[dict]:
        with self._lock:
            entry = self._data.get(conversation_id)
            if not entry or time.time() - entry[0] > TTL_SECONDS:
                self._data.pop(conversation_id, None)
                return []
            return list(entry[1])

    def append(self, conversation_id: str, turn: dict) -> None:
        with self._lock:
            turns = self._data.get(conversation_id, (0, []))[1]
            self._data[conversation_id] = (time.time(), (turns + [turn])[-MAX_TURNS:])

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._data.pop(conversation_id, None)


class RedisStore:
    mode = "redis"

    def __init__(self, client):
        self.r = client

    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"ecuery:conversation:{conversation_id}"

    def history(self, conversation_id: str) -> list[dict]:
        return [json.loads(t) for t in self.r.lrange(self._key(conversation_id), 0, -1)]

    def append(self, conversation_id: str, turn: dict) -> None:
        key = self._key(conversation_id)
        pipe = self.r.pipeline()
        pipe.rpush(key, json.dumps(turn, ensure_ascii=False))
        pipe.ltrim(key, -MAX_TURNS, -1)
        pipe.expire(key, TTL_SECONDS)
        pipe.execute()

    def clear(self, conversation_id: str) -> None:
        self.r.delete(self._key(conversation_id))


def new_conversation_id() -> str:
    return uuid.uuid4().hex


_store: MemoryStore | None = None
_redis = None


def redis_client():
    """Shared Redis connection (conversation memory + query cache), or None without REDIS_URL."""
    global _redis
    if _redis is None and os.getenv("REDIS_URL"):
        import redis

        _redis = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True, socket_timeout=5)
        _redis.ping()  # fail loudly at startup rather than silently losing memory later
    return _redis


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        client = redis_client()
        _store = RedisStore(client) if client else InMemoryStore()
    return _store
