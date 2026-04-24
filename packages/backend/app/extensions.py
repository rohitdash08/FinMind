import fnmatch
import time

from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
import redis
from redis.exceptions import RedisError

from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()


class ResilientRedis:
    """Redis facade with an in-process fallback for local/free-tier outages."""

    def __init__(self, url: str):
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._fallback: dict[str, tuple[str, float | None]] = {}

    def get(self, key: str):
        try:
            return self._client.get(key)
        except RedisError:
            return self._fallback_get(key)

    def set(self, key: str, value):
        try:
            return self._client.set(key, value)
        except RedisError:
            self._fallback[key] = (str(value), None)
            return True

    def setex(self, key: str, ttl_seconds: int, value):
        try:
            return self._client.setex(key, ttl_seconds, value)
        except RedisError:
            self._fallback[key] = (str(value), time.time() + int(ttl_seconds))
            return True

    def delete(self, *keys: str):
        try:
            return self._client.delete(*keys)
        except RedisError:
            deleted = 0
            for key in keys:
                if key in self._fallback:
                    deleted += 1
                    self._fallback.pop(key, None)
            return deleted

    def scan(self, cursor=0, match=None, count=100):
        try:
            return self._client.scan(cursor=cursor, match=match, count=count)
        except RedisError:
            self._purge_expired()
            keys = list(self._fallback.keys())
            if match:
                keys = [key for key in keys if fnmatch.fnmatch(key, match)]
            return 0, keys

    def _fallback_get(self, key: str):
        self._purge_expired()
        entry = self._fallback.get(key)
        return entry[0] if entry else None

    def _purge_expired(self):
        now = time.time()
        expired = [key for key, (_, expires_at) in self._fallback.items() if expires_at and expires_at <= now]
        for key in expired:
            self._fallback.pop(key, None)


_settings = Settings()
redis_client = ResilientRedis(_settings.redis_url)
