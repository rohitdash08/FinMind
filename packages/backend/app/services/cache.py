"""
Smart caching strategy for FinMind dashboard & analytics.
Issue #127: Optimize performance with intelligent cache invalidation.

Implements a multi-layer caching strategy:
1. Per-request in-memory cache (request-scoped, zero Redis calls for repeated access)
2. Redis short-lived cache (TTL-based, for frequent reads)
3. Tag-based invalidation (invalidate all caches for a user on write)
4. Graceful degradation (returns None on Redis failure instead of crashing)
"""

from __future__ import annotations
import json
import logging
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger("finmind.cache")

# Default TTL values by cache type (seconds)
TTL_MONTHLY_SUMMARY = 300       # 5 min: expensive aggregate, invalidated on expense write
TTL_DASHBOARD_SUMMARY = 300     # 5 min
TTL_CATEGORIES = 3600           # 1 hour: rarely changes
TTL_UPCOMING_BILLS = 600        # 10 min: bills change infrequently
TTL_INSIGHTS = 3600             # 1 hour: monthly analytics, expensive to compute
TTL_SHORT = 60                  # 1 min: for rapidly-changing data
TTL_LONG = 86400                # 24 hours: for near-static data

# ── Key helpers ─────────────────────────────────────────────────────────────

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


def user_tag_key(user_id: int) -> str:
    """Tag key: stores set of all cache keys for a user. Used for bulk invalidation."""
    return f"user:{user_id}:cache_tags"


# ── Redis helpers with graceful degradation ──────────────────────────────────

def _redis():
    """Get Redis client from extensions, returns None if unavailable."""
    try:
        from ..extensions import redis_client
        return redis_client
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl_seconds: Optional[int] = None, user_id: Optional[int] = None) -> bool:
    """
    Set a cache value with optional TTL and user tag registration.

    Args:
        key: Cache key.
        value: JSON-serializable value.
        ttl_seconds: TTL in seconds. None = no expiry.
        user_id: If provided, registers key in user's tag set for bulk invalidation.

    Returns:
        True on success, False on Redis failure (graceful degradation).
    """
    r = _redis()
    if r is None:
        return False
    try:
        payload = json.dumps(value, default=str)
        if ttl_seconds:
            r.setex(key, ttl_seconds, payload)
        else:
            r.set(key, payload)
        # Register key in user tag for bulk invalidation
        if user_id is not None:
            tag_key = user_tag_key(user_id)
            r.sadd(tag_key, key)
            # Tag set should expire after 7 days to prevent unbounded growth
            r.expire(tag_key, 604800)
        return True
    except Exception as exc:
        logger.warning("cache_set failed key=%s: %s", key, exc)
        return False


def cache_get(key: str) -> Any:
    """
    Get a cached value.

    Returns:
        Deserialized value, or None if not found or Redis unavailable.
    """
    r = _redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("cache_get failed key=%s: %s", key, exc)
        return None


def cache_delete(key: str) -> bool:
    """Delete a single cache key."""
    r = _redis()
    if r is None:
        return False
    try:
        r.delete(key)
        return True
    except Exception as exc:
        logger.warning("cache_delete failed key=%s: %s", key, exc)
        return False


def cache_delete_patterns(patterns: Iterable[str]) -> int:
    """
    Delete all keys matching any of the given glob patterns.
    Uses SCAN to avoid blocking Redis on large keyspaces.

    Returns:
        Total number of keys deleted.
    """
    r = _redis()
    if r is None:
        return 0
    deleted = 0
    for pattern in patterns:
        try:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("cache_delete_patterns failed pattern=%s: %s", pattern, exc)
    return deleted


def invalidate_user_cache(user_id: int) -> int:
    """
    Invalidate ALL cached data for a user using tag-based lookup.
    Called after any write operation (expense create/update/delete, bill changes, etc.)

    Returns:
        Number of keys deleted.
    """
    r = _redis()
    if r is None:
        return 0
    try:
        tag_key = user_tag_key(user_id)
        keys = r.smembers(tag_key)
        if not keys:
            # Fallback: delete by pattern
            return cache_delete_patterns([
                f"user:{user_id}:*",
                f"insights:{user_id}:*",
            ])
        pipe = r.pipeline()
        for key in keys:
            pipe.delete(key)
        pipe.delete(tag_key)
        results = pipe.execute()
        deleted = sum(1 for r in results if r == 1)
        logger.debug("invalidate_user_cache user=%s deleted=%s keys", user_id, deleted)
        return deleted
    except Exception as exc:
        logger.warning("invalidate_user_cache failed user=%s: %s", user_id, exc)
        return 0


def cache_or_compute(
    key: str,
    compute_fn: Callable[[], Any],
    ttl_seconds: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Any:
    """
    Cache-aside pattern: return cached value or compute and cache.

    Args:
        key: Cache key.
        compute_fn: Callable that returns the value to cache.
        ttl_seconds: TTL for the cached value.
        user_id: For tag registration.

    Returns:
        Cached or freshly computed value.
    """
    cached = cache_get(key)
    if cached is not None:
        return cached
    value = compute_fn()
    if value is not None:
        cache_set(key, value, ttl_seconds=ttl_seconds, user_id=user_id)
    return value


def get_cache_stats(user_id: Optional[int] = None) -> dict:
    """
    Get cache statistics for monitoring.

    Returns:
        Dict with hit rate info, key counts, and memory usage if available.
    """
    r = _redis()
    if r is None:
        return {"available": False}
    try:
        info = r.info("stats")
        memory = r.info("memory")
        stats = {
            "available": True,
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate": (
                round(
                    info.get("keyspace_hits", 0)
                    / max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1)
                    * 100,
                    2,
                )
            ),
            "used_memory_mb": round(memory.get("used_memory", 0) / 1024 / 1024, 2),
            "peak_memory_mb": round(memory.get("used_memory_peak", 0) / 1024 / 1024, 2),
        }
        if user_id is not None:
            tag_key = user_tag_key(user_id)
            stats["user_cached_keys"] = r.scard(tag_key)
        return stats
    except Exception as exc:
        logger.warning("get_cache_stats failed: %s", exc)
        return {"available": True, "error": str(exc)}