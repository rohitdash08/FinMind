import json
import logging
from typing import Iterable

from redis.exceptions import RedisError

from ..extensions import redis_client

logger = logging.getLogger("finmind.cache")
_fallback_cache: dict[str, str] = {}


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
        logger.warning("Redis unavailable; skipping cache set")


def cache_get(key: str):
    try:
        raw = redis_client.get(key)
    except RedisError:
        raw = _fallback_cache.get(key)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw) if raw else None


def cache_delete_patterns(patterns: Iterable[str]):
    for pattern in patterns:
        _fallback_delete_pattern(pattern)
        try:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
        except RedisError:
            logger.warning("Redis unavailable while deleting cache pattern=%s", pattern)


def _fallback_delete_pattern(pattern: str):
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        for key in list(_fallback_cache):
            if key.startswith(prefix):
                _fallback_cache.pop(key, None)
    else:
        _fallback_cache.pop(pattern, None)
