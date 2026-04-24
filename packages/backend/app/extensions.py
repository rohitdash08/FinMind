from __future__ import annotations

import fnmatch
import time

from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
from redis.exceptions import RedisError

from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()


class ResilientRedis:
    """Small Redis wrapper that falls back to in-memory storage when Redis is down.

    Free-tier/dev deployments and tests often run without a reachable Redis host.
    The app should keep auth/session/cache flows functional instead of failing every
    request on DNS/connection errors.
    """

    def __init__(self, url: str):
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._memory: dict[str, tuple[str, float | None]] = {}
        self._use_memory = False

    def get(self, key: str):
        if not self._use_memory:
            try:
                return self._client.get(key)
            except RedisError:
                self._use_memory = True
        self._purge_expired()
        item = self._memory.get(key)
        return item[0] if item else None

    def setex(self, key: str, ttl: int, value):
        if not self._use_memory:
            try:
                return self._client.setex(key, ttl, value)
            except RedisError:
                self._use_memory = True
        self._memory[key] = (str(value), time.time() + max(int(ttl), 1))
        return True

    def set(self, key: str, value, ex: int | None = None, **kwargs):
        if not self._use_memory:
            try:
                return self._client.set(key, value, ex=ex, **kwargs)
            except RedisError:
                self._use_memory = True
        expires_at = time.time() + int(ex) if ex else None
        self._memory[key] = (str(value), expires_at)
        return True

    def delete(self, *keys: str):
        if not self._use_memory:
            try:
                return self._client.delete(*keys)
            except RedisError:
                self._use_memory = True
        deleted = 0
        for key in keys:
            if key in self._memory:
                deleted += 1
                self._memory.pop(key, None)
        return deleted

    def keys(self, pattern: str = "*"):
        if not self._use_memory:
            try:
                return self._client.keys(pattern)
            except RedisError:
                self._use_memory = True
        self._purge_expired()
        return [key for key in self._memory if fnmatch.fnmatch(key, pattern)]

    def scan(self, cursor: int = 0, match: str | None = None, count: int | None = None):
        if not self._use_memory:
            try:
                return self._client.scan(cursor=cursor, match=match, count=count)
            except RedisError:
                self._use_memory = True
        keys = self.keys(match or "*")
        return 0, keys

    def ping(self):
        if not self._use_memory:
            try:
                return self._client.ping()
            except RedisError:
                self._use_memory = True
        return True

    def _purge_expired(self):
        now = time.time()
        expired = [key for key, (_, exp) in self._memory.items() if exp and exp <= now]
        for key in expired:
            self._memory.pop(key, None)


_settings = Settings()
redis_client = ResilientRedis(_settings.redis_url)
