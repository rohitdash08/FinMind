import json
import time
from typing import Iterable

from redis.exceptions import RedisError

from ..extensions import redis_client

# Small in-process fallback keeps tests/local dev usable when Redis is down.
_MEMORY_CACHE: dict[str, tuple[float | None, str]] = {}
_CACHE_STATS = {"hits": 0, "misses": 0, "sets": 0, "invalidations": 0, "fallback_errors": 0}


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


def dashboard_cache_patterns(user_id: int, ym: str | None = None) -> list[str]:
    """Return all cache keys touched by dashboard/analytics data changes."""
    patterns = [f"user:{user_id}:dashboard_summary:*", f"insights:{user_id}:*"]
    if ym:
        patterns.append(monthly_summary_key(user_id, ym))
    else:
        patterns.append(f"user:{user_id}:monthly_summary:*")
    return patterns


def cache_set(key: str, value, ttl_seconds: int | None = None, tags: Iterable[str] | None = None):
    payload = json.dumps(
        {
            "value": value,
            "cached_at": int(time.time()),
            "ttl_seconds": ttl_seconds,
            "tags": sorted(set(tags or [])),
        }
    )
    _CACHE_STATS["sets"] += 1
    try:
        if ttl_seconds:
            redis_client.setex(key, ttl_seconds, payload)
        else:
            redis_client.set(key, payload)
    except RedisError:
        _CACHE_STATS["fallback_errors"] += 1
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        _MEMORY_CACHE[key] = (expires_at, payload)


def cache_get(key: str, with_meta: bool = False):
    raw = None
    try:
        raw = redis_client.get(key)
    except RedisError:
        _CACHE_STATS["fallback_errors"] += 1
        entry = _MEMORY_CACHE.get(key)
        if entry:
            expires_at, raw = entry
            if expires_at is not None and expires_at <= time.time():
                _MEMORY_CACHE.pop(key, None)
                raw = None
    if not raw:
        _CACHE_STATS["misses"] += 1
        return (None, None) if with_meta else None
    _CACHE_STATS["hits"] += 1
    decoded = json.loads(raw)
    # Backward compatible with older cache entries that stored raw payloads.
    if isinstance(decoded, dict) and "value" in decoded and "cached_at" in decoded:
        return (decoded["value"], decoded) if with_meta else decoded["value"]
    return (decoded, None) if with_meta else decoded


def cache_delete_patterns(patterns: Iterable[str]):
    for pattern in patterns:
        _CACHE_STATS["invalidations"] += 1
        _delete_memory_pattern(pattern)
        try:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
        except RedisError:
            _CACHE_STATS["fallback_errors"] += 1


def cache_stats() -> dict:
    return {**_CACHE_STATS, "memory_keys": len(_MEMORY_CACHE)}


def _delete_memory_pattern(pattern: str) -> None:
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        for key in list(_MEMORY_CACHE):
            if key.startswith(prefix):
                _MEMORY_CACHE.pop(key, None)
    else:
        _MEMORY_CACHE.pop(pattern, None)
