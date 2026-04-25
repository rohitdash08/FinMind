from __future__ import annotations

import fnmatch
import time
from typing import Any

import redis
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy

from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()


class ResilientRedis:
    """Redis facade with an in-memory fallback for local tests/free-tier outages."""

    def __init__(self, url: str, decode_responses: bool = True):
        self._client = redis.Redis.from_url(url, decode_responses=decode_responses)
        self._fallback: dict[str, tuple[Any, float | None]] = {}
        self._using_fallback = False

    def get(self, key: str):
        try:
            return self._client.get(key)
        except redis.RedisError:
            self._using_fallback = True
            return self._fallback_get(key)

    def set(self, key: str, value: Any):
        try:
            return self._client.set(key, value)
        except redis.RedisError:
            self._using_fallback = True
            self._fallback[key] = (value, None)
            return True

    def setex(self, key: str, ttl_seconds: int, value: Any):
        try:
            return self._client.setex(key, ttl_seconds, value)
        except redis.RedisError:
            self._using_fallback = True
            self._fallback[key] = (value, time.time() + max(int(ttl_seconds), 1))
            return True

    def delete(self, *keys: str):
        try:
            return self._client.delete(*keys)
        except redis.RedisError:
            self._using_fallback = True
            deleted = 0
            for key in keys:
                deleted += 1 if self._fallback.pop(key, None) is not None else 0
            return deleted

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100):
        try:
            return self._client.scan(cursor=cursor, match=match, count=count)
        except redis.RedisError:
            self._using_fallback = True
            self._purge_expired()
            keys = list(self._fallback.keys())
            if match:
                keys = [key for key in keys if fnmatch.fnmatch(key, match)]
            return 0, keys[:count]

    def flushdb(self):
        try:
            return self._client.flushdb()
        except redis.RedisError:
            self._using_fallback = True
            self._fallback.clear()
            return True

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
        for key, (_, expires_at) in list(self._fallback.items()):
            if expires_at is not None and expires_at <= now:
                self._fallback.pop(key, None)


_settings = Settings()
redis_client = ResilientRedis(_settings.redis_url, decode_responses=True)
