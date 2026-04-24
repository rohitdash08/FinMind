from fnmatch import fnmatch
import time

from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
from redis.exceptions import RedisError

from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()


class ResilientRedis:
    """Redis facade with an in-memory fallback for local/dev/test availability."""

    def __init__(self, url: str):
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._memory: dict[str, tuple[float | None, str]] = {}
        self.fallback_errors = 0

    def setex(self, key: str, ttl: int, value) -> bool:
        try:
            return bool(self._client.setex(key, ttl, value))
        except RedisError:
            self.fallback_errors += 1
            self._memory[key] = (time.time() + int(ttl), str(value))
            return True

    def set(self, key: str, value) -> bool:
        try:
            return bool(self._client.set(key, value))
        except RedisError:
            self.fallback_errors += 1
            self._memory[key] = (None, str(value))
            return True

    def get(self, key: str):
        try:
            return self._client.get(key)
        except RedisError:
            self.fallback_errors += 1
            entry = self._memory.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at is not None and expires_at <= time.time():
                self._memory.pop(key, None)
                return None
            return value

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._memory:
                self._memory.pop(key, None)
                deleted += 1
        try:
            deleted += int(self._client.delete(*keys)) if keys else 0
        except RedisError:
            self.fallback_errors += 1
        return deleted

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100):
        try:
            return self._client.scan(cursor=cursor, match=match, count=count)
        except RedisError:
            self.fallback_errors += 1
            if cursor != 0:
                return 0, []
            self._purge_expired()
            keys = [k for k in self._memory if match is None or fnmatch(k, match)]
            return 0, keys

    def _purge_expired(self) -> None:
        now = time.time()
        for key, (expires_at, _) in list(self._memory.items()):
            if expires_at is not None and expires_at <= now:
                self._memory.pop(key, None)


_settings = Settings()
redis_client = ResilientRedis(_settings.redis_url)
