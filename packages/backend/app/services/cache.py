import json
import time
from typing import Iterable

from redis.exceptions import RedisError

from ..extensions import redis_client

_LOCAL_CACHE: dict[str, tuple[str, float | None]] = {}


def monthly_summary_key(user_id: int, ym: str) -> str:
    return f"user:{user_id}:monthly_summary:{ym}"


def categories_key(user_id: int) -> str:
    return f"user:{user_id}:categories"


def upcoming_bills_key(user_id: int) -> str:
    return f"user:{user_id}:upcoming_bills"


def insights_key(user_id: int, ym: str) -> str:
    return f"insights:{user_id}:{ym}"


def dashboard_summary_key(user_id: int, ym: str) -> str:
    return f"user:{user_id}:dashboard_summary:{ym}"


def cache_set(key: str, value, ttl_seconds: int | None = None):
    payload = json.dumps(value)
    try:
        if ttl_seconds:
            redis_client.setex(key, ttl_seconds, payload)
        else:
            redis_client.set(key, payload)
    except RedisError:
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        _LOCAL_CACHE[key] = (payload, expires_at)


def cache_get(key: str):
    try:
        raw = redis_client.get(key)
    except RedisError:
        cached = _LOCAL_CACHE.get(key)
        if not cached:
            return None
        raw, expires_at = cached
        if expires_at and expires_at <= time.time():
            _LOCAL_CACHE.pop(key, None)
            return None
    return json.loads(raw) if raw else None


def cache_delete_patterns(patterns: Iterable[str]):
    for pattern in patterns:
        try:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
        except RedisError:
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                for key in list(_LOCAL_CACHE):
                    if key.startswith(prefix):
                        _LOCAL_CACHE.pop(key, None)
            else:
                _LOCAL_CACHE.pop(pattern, None)
