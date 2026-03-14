"""
Smart caching strategy for dashboard & analytics (Issue #127).

Architecture:
- Tiered TTLs: static data (long) vs live data (short) vs AI results (medium)
- cache() decorator for route-level caching with auto key generation
- Explicit invalidation on mutations (existing pattern extended)
- Cache stats endpoint for monitoring
- Graceful degradation: cache errors never crash the app
"""

from __future__ import annotations

import functools
import json
import logging
import time
from typing import Any, Callable, Iterable

from flask import request as flask_request
from flask_jwt_extended import get_jwt_identity

from ..extensions import redis_client

logger = logging.getLogger("finmind.cache")


# ── TTL constants ─────────────────────────────────────────────────────────────

class TTL:
    """Tiered TTL strategy: match cache lifetime to data volatility."""
    STATIC    = 3600       # 1 hour  — categories, user prefs
    ANALYTICS = 600        # 10 min  — monthly summaries, insights
    DASHBOARD = 300        # 5 min   — dashboard summary
    AI_RESULT = 1800       # 30 min  — AI budget suggestions (expensive)
    SHORT     = 60         # 1 min   — upcoming bills, reminders count
    REALTIME  = 0          # no cache


# ── Key builders ─────────────────────────────────────────────────────────────

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

def budget_suggestion_key(user_id: int, ym: str) -> str:
    return f"ai:budget_suggestion:{user_id}:{ym}"


# ── Core cache operations ─────────────────────────────────────────────────────

def cache_set(key: str, value: Any, ttl_seconds: int | None = None) -> bool:
    """Set a cache value. Returns True on success, False on error."""
    try:
        payload = json.dumps(value)
        if ttl_seconds and ttl_seconds > 0:
            redis_client.setex(key, ttl_seconds, payload)
        else:
            redis_client.set(key, payload)
        return True
    except Exception as exc:
        logger.warning("cache_set failed key=%s: %s", key, exc)
        return False


def cache_get(key: str) -> Any | None:
    """Get a cache value. Returns None on miss or error."""
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("cache_get failed key=%s: %s", key, exc)
        return None


def cache_delete(key: str) -> bool:
    """Delete a single cache key."""
    try:
        redis_client.delete(key)
        return True
    except Exception as exc:
        logger.warning("cache_delete failed key=%s: %s", key, exc)
        return False


def cache_delete_patterns(patterns: Iterable[str]) -> int:
    """Delete all keys matching any of the given patterns. Returns count deleted."""
    total = 0
    for pattern in patterns:
        try:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    redis_client.delete(*keys)
                    total += len(keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("cache_delete_patterns failed pattern=%s: %s", pattern, exc)
    return total


# ── Decorator ─────────────────────────────────────────────────────────────────

def cached(key_fn: Callable[..., str], ttl: int = TTL.ANALYTICS):
    """
    Route-level caching decorator.

    Usage:
        @bp.get("/data")
        @jwt_required()
        @cached(lambda: f"mykey:{get_jwt_identity()}", ttl=TTL.ANALYTICS)
        def my_route():
            ...

    key_fn is called at request time so it can access flask context.
    If cache is warm, returns cached JSON directly.
    On miss: calls the wrapped function and caches its response.
    Cache errors never raise — they silently degrade.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = None
            try:
                key = key_fn()
                hit = cache_get(key)
                if hit is not None:
                    logger.debug("cache HIT key=%s", key)
                    _increment_hit()
                    from flask import jsonify as _jsonify
                    return _jsonify(hit)
                _increment_miss()
            except Exception as exc:
                logger.warning("cache lookup failed key=%s: %s", key, exc)

            result = fn(*args, **kwargs)

            try:
                if key and result.status_code == 200:
                    data = result.get_json(force=True)
                    cache_set(key, data, ttl_seconds=ttl)
                    logger.debug("cache SET key=%s ttl=%s", key, ttl)
            except Exception as exc:
                logger.warning("cache store failed key=%s: %s", key, exc)

            return result
        return wrapper
    return decorator


# ── Stats ─────────────────────────────────────────────────────────────────────

_STATS_KEY = "cache:stats"


def _increment_hit():
    try:
        redis_client.hincrby(_STATS_KEY, "hits", 1)
    except Exception:
        pass


def _increment_miss():
    try:
        redis_client.hincrby(_STATS_KEY, "misses", 1)
    except Exception:
        pass


def get_cache_stats() -> dict:
    """Return cache hit/miss counters and Redis info."""
    try:
        raw = redis_client.hgetall(_STATS_KEY)
        hits = int(raw.get(b"hits", 0))
        misses = int(raw.get(b"misses", 0))
        total = hits + misses
        hit_rate = round(hits / total * 100, 1) if total > 0 else 0.0
        info = redis_client.info("memory")
        return {
            "hits": hits,
            "misses": misses,
            "total_requests": total,
            "hit_rate_percent": hit_rate,
            "redis_used_memory_human": info.get("used_memory_human", "unknown"),
        }
    except Exception as exc:
        logger.warning("get_cache_stats failed: %s", exc)
        return {"error": str(exc)}


def reset_cache_stats() -> None:
    try:
        redis_client.delete(_STATS_KEY)
    except Exception:
        pass
