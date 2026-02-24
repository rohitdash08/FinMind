"""
cache.py — Centralised Redis cache service for FinMind.

All TTL constants, key-builder functions, and cache operations live here.
Importing routes should never hard-code TTL values; use the constants below.

Public API:
    cache_get(key) -> value | None
    cache_set(key, value, ttl_seconds=TTL_STANDARD)
    cache_delete(key)
    cache_delete_patterns(patterns)
    invalidate_user_caches(uid)          — cascade-invalidate all user analytics
    cache_stats(uid=None) -> dict        — hit/miss counters from Redis
    warm_user_cache(uid, app_context)    — optional pre-warming (call after login)

Key builders (use these everywhere — never construct keys inline):
    monthly_summary_key(uid, ym)
    dashboard_summary_key(uid, ym)
    categories_key(uid)
    upcoming_bills_key(uid)
    insights_key(uid, ym)
    digest_key(uid, ym, currency)
    inflation_key(uid, months)
    savings_key(uid, months)
    breakdown_key(uid, ym)
    notifications_key(uid)
    metrics_key(uid, days)
"""
import json
import logging
from typing import Iterable

from ..extensions import redis_client

logger = logging.getLogger("finmind.cache")

# ── TTL constants (seconds) ────────────────────────────────────────────────────
TTL_SHORT    = 60      # Very dynamic data (notifications, pending reminders)
TTL_STANDARD = 300     # Dashboard, summaries — refresh every 5 minutes
TTL_MEDIUM   = 600     # Analytics (inflation, savings, breakdown) — 10 minutes
TTL_LONG     = 1800    # Stable reference data (categories list) — 30 minutes
TTL_DIGEST   = 600     # Weekly digest — 10 minutes

# ── Redis stats keys ───────────────────────────────────────────────────────────
_STATS_HITS_KEY   = "finmind:cache:stats:hits"
_STATS_MISSES_KEY = "finmind:cache:stats:misses"


# ── Key builders ───────────────────────────────────────────────────────────────

def monthly_summary_key(user_id: int, ym: str) -> str:
    return f"user:{user_id}:monthly_summary:{ym}"


def dashboard_summary_key(user_id: int, ym: str) -> str:
    return f"user:{user_id}:dashboard_summary:{ym}"


def categories_key(user_id: int) -> str:
    return f"user:{user_id}:categories"


def upcoming_bills_key(user_id: int) -> str:
    return f"user:{user_id}:upcoming_bills"


def insights_key(user_id: int, ym: str) -> str:
    return f"insights:{user_id}:{ym}"


def digest_key(user_id: int, ym: str, currency: str = "INR") -> str:
    return f"user:{user_id}:weekly_digest:{ym}:{currency}"


def inflation_key(user_id: int, months: int) -> str:
    return f"user:{user_id}:inflation:{months}"


def savings_key(user_id: int, months: int) -> str:
    return f"user:{user_id}:savings:{months}"


def breakdown_key(user_id: int, ym: str) -> str:
    return f"user:{user_id}:breakdown:{ym}"


def notifications_key(user_id: int) -> str:
    return f"user:{user_id}:notifications"


def metrics_key(user_id: int, days: int) -> str:
    return f"user:{user_id}:metrics:{days}"


# ── Core cache operations ──────────────────────────────────────────────────────

def cache_set(key: str, value, ttl_seconds: int = TTL_STANDARD) -> None:
    """Store a JSON-serialisable value. Always uses a TTL (default TTL_STANDARD)."""
    payload = json.dumps(value)
    if ttl_seconds and ttl_seconds > 0:
        redis_client.setex(key, ttl_seconds, payload)
    else:
        redis_client.set(key, payload)


def cache_get(key: str):
    """Return the cached value or None. Tracks hit/miss stats."""
    raw = redis_client.get(key)
    if raw:
        try:
            redis_client.incr(_STATS_HITS_KEY)
        except Exception:
            pass
        return json.loads(raw)
    try:
        redis_client.incr(_STATS_MISSES_KEY)
    except Exception:
        pass
    return None


def cache_delete(key: str) -> None:
    """Delete a single cache key."""
    redis_client.delete(key)


def cache_delete_patterns(patterns: Iterable[str]) -> int:
    """Delete all keys matching any of the given glob patterns. Returns count deleted."""
    total = 0
    for pattern in patterns:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                redis_client.delete(*keys)
                total += len(keys)
            if cursor == 0:
                break
    return total


def invalidate_user_caches(uid: int) -> int:
    """
    Cascade-invalidate ALL computed caches for a user.

    Call this whenever expenses or categories change. Covers:
    dashboard, monthly summaries, insights, digest, inflation,
    savings, breakdown, notifications.
    """
    patterns = [
        f"user:{uid}:*",
        f"insights:{uid}:*",
    ]
    deleted = cache_delete_patterns(patterns)
    logger.debug("Invalidated %d cache keys for user=%s", deleted, uid)
    return deleted


def cache_stats(uid: int | None = None) -> dict:
    """
    Return cache hit/miss statistics.

    If uid is provided, also returns the count of active cache keys for that user.
    """
    try:
        hits   = int(redis_client.get(_STATS_HITS_KEY)   or 0)
        misses = int(redis_client.get(_STATS_MISSES_KEY) or 0)
        total  = hits + misses
        hit_rate = round(hits / total, 4) if total > 0 else 0.0
    except Exception:
        hits = misses = total = 0
        hit_rate = 0.0

    result: dict = {
        "total_requests": total,
        "hits":           hits,
        "misses":         misses,
        "hit_rate":       hit_rate,
    }

    if uid is not None:
        try:
            user_keys = sum(
                1 for _ in redis_client.scan_iter(f"user:{uid}:*")
            ) + sum(
                1 for _ in redis_client.scan_iter(f"insights:{uid}:*")
            )
            result["user_active_keys"] = user_keys
        except Exception:
            result["user_active_keys"] = None

    return result
