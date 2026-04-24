from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
from redis.exceptions import RedisError
from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()


class ResilientRedis:
    """Redis client wrapper with in-memory fallback for local/free-tier outages."""

    def __init__(self, url: str):
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._fallback: dict[str, str] = {}

    def get(self, key: str):
        try:
            return self._client.get(key)
        except RedisError:
            return self._fallback.get(key)

    def set(self, key: str, value: str):
        try:
            return self._client.set(key, value)
        except RedisError:
            self._fallback[key] = value
            return True

    def setex(self, key: str, _ttl: int, value: str):
        try:
            return self._client.setex(key, _ttl, value)
        except RedisError:
            self._fallback[key] = value
            return True

    def delete(self, *keys: str):
        try:
            return self._client.delete(*keys)
        except RedisError:
            removed = 0
            for key in keys:
                removed += 1 if self._fallback.pop(key, None) is not None else 0
            return removed

    def scan(self, cursor=0, match=None, count=None):
        try:
            return self._client.scan(cursor=cursor, match=match, count=count)
        except RedisError:
            import fnmatch

            keys = list(self._fallback)
            if match:
                keys = [key for key in keys if fnmatch.fnmatch(key, match)]
            return 0, keys

    def flushdb(self):
        try:
            return self._client.flushdb()
        except RedisError:
            self._fallback.clear()
            return True


_settings = Settings()
redis_client = ResilientRedis(_settings.redis_url)
