from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import fnmatch
import os
import time
import redis
from flask import Flask


db = SQLAlchemy()
jwt = JWTManager()


class InMemoryRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self._expiries: dict[str, float] = {}

    def _evict_if_expired(self, key: str) -> None:
        expiry = self._expiries.get(key)
        if expiry is not None and expiry <= time.time():
            self._store.pop(key, None)
            self._expiries.pop(key, None)

    def _purge_expired(self) -> None:
        for key in list(self._store.keys()):
            self._evict_if_expired(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        self._store[key] = value
        self._expiries[key] = time.time() + max(int(ttl_seconds), 1)
        return True

    def set(self, key: str, value: str) -> bool:
        self._store[key] = value
        self._expiries.pop(key, None)
        return True

    def get(self, key: str):
        self._evict_if_expired(key)
        return self._store.get(key)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._store:
                deleted += 1
            self._store.pop(key, None)
            self._expiries.pop(key, None)
        return deleted

    def flushdb(self) -> bool:
        self._store.clear()
        self._expiries.clear()
        return True

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100):
        self._purge_expired()
        keys = sorted(self._store.keys())
        if match:
            keys = [key for key in keys if fnmatch.fnmatch(key, match)]
        start = int(cursor)
        size = max(int(count), 1)
        batch = keys[start : start + size]
        next_cursor = 0 if start + size >= len(keys) else start + size
        return next_cursor, batch


class RedisClientProxy:
    def __init__(self):
        self._client = InMemoryRedis()

    def set_client(self, client) -> None:
        self._client = client

    def __getattr__(self, name: str):
        return getattr(self._client, name)


redis_client = RedisClientProxy()


def _resolve_redis_url(app: Flask) -> str:
    explicit_url = os.getenv("REDIS_URL") or app.config.get("REDIS_URL")
    if explicit_url:
        return explicit_url

    host = os.getenv("REDIS_HOST") or app.config.get("REDIS_HOST") or "localhost"
    port = os.getenv("REDIS_PORT") or app.config.get("REDIS_PORT") or 6379
    db_index = os.getenv("REDIS_DB") or app.config.get("REDIS_DB") or 0

    return f"redis://{host}:{int(port)}/{int(db_index)}"


def init_redis(app: Flask) -> None:
    if app.config.get("TESTING", False):
        try:
            import fakeredis

            redis_client.set_client(fakeredis.FakeStrictRedis(decode_responses=True))
            return
        except Exception:
            redis_client.set_client(InMemoryRedis())
            return

    redis_url = _resolve_redis_url(app)
    redis_client.set_client(redis.Redis.from_url(redis_url, decode_responses=True))
