from __future__ import annotations

import fnmatch
import time

from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()


class ResilientRedisClient:
    """Redis facade with an in-memory fallback for dev/test availability.

    Production deployments still use the configured Redis server. If Redis is
    temporarily unreachable, cache/session calls degrade to a process-local store
    instead of failing hot-path API requests.
    """

    def __init__(self, url: str):
        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._fallback: dict[str, tuple[str, float | None]] = {}

    def setex(self, key: str, ttl_seconds: int, value) -> bool:
        try:
            return bool(self._redis.setex(key, ttl_seconds, value))
        except redis.exceptions.RedisError:
            self._fallback[key] = (str(value), time.time() + int(ttl_seconds))
            return True

    def set(self, key: str, value) -> bool:
        try:
            return bool(self._redis.set(key, value))
        except redis.exceptions.RedisError:
            self._fallback[key] = (str(value), None)
            return True

    def get(self, key: str):
        try:
            return self._redis.get(key)
        except redis.exceptions.RedisError:
            return self._fallback_get(key)

    def delete(self, *keys: str) -> int:
        try:
            return int(self._redis.delete(*keys))
        except redis.exceptions.RedisError:
            deleted = 0
            for key in keys:
                if key in self._fallback:
                    deleted += 1
                    self._fallback.pop(key, None)
            return deleted

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100):
        try:
            return self._redis.scan(cursor=cursor, match=match, count=count)
        except redis.exceptions.RedisError:
            self._purge_expired()
            keys = list(self._fallback.keys())
            if match:
                keys = [key for key in keys if fnmatch.fnmatch(key, match)]
            start = int(cursor or 0)
            end = start + count
            next_cursor = 0 if end >= len(keys) else end
            return next_cursor, keys[start:end]

    def _fallback_get(self, key: str):
        item = self._fallback.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at <= time.time():
            self._fallback.pop(key, None)
            return None
        return value

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [
            key
            for key, (_value, expires_at) in self._fallback.items()
            if expires_at is not None and expires_at <= now
        ]
        for key in expired:
            self._fallback.pop(key, None)


_settings = Settings()
redis_client = ResilientRedisClient(_settings.redis_url)
