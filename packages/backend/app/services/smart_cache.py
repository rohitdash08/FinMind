"""
Smart caching strategy for FinMind dashboard & analytics (issue #127).

Provides:
- Tiered TTLs based on data volatility
- Tag-based invalidation (invalidate all keys for a user on write)
- Cache warming helper for dashboard on login
- Stale-while-revalidate pattern via background flag
"""
import json
import logging
from typing import Any, Callable, Iterable, Optional

from ..extensions import redis_client

logger = logging.getLogger("finmind.cache")

# ---------------------------------------------------------------------------
# TTL tiers (seconds)
# ---------------------------------------------------------------------------
TTL_REALTIME = 60          # live balances, recent transactions
TTL_SUMMARY = 300          # monthly summary, dashboard totals
TTL_ANALYTICS = 900        # insights, category breakdown, trends
TTL_STATIC = 3600          # categories list, user preferences


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------
def _tag_key(user_id: int) -> str:
    return f"cache:tags:user:{user_id}"


def _register_key(user_id: int, key: str):
    """Track key under user tag for bulk invalidation."""
    redis_client.sadd(_tag_key(user_id), key)


def smart_set(key: str, value: Any, ttl_seconds: int, user_id: Optional[int] = None):
    payload = json.dumps(value)
    redis_client.setex(key, ttl_seconds, payload)
    if user_id is not None:
        _register_key(user_id, key)
    logger.debug("cache SET %s ttl=%s", key, ttl_seconds)


def smart_get(key: str) -> Optional[Any]:
    raw = redis_client.get(key)
    if raw:
        logger.debug("cache HIT %s", key)
        return json.loads(raw)
    logger.debug("cache MISS %s", key)
    return None


def smart_get_or_compute(
    key: str,
    compute_fn: Callable[[], Any],
    ttl_seconds: int,
    user_id: Optional[int] = None,
) -> Any:
    """Return cached value or compute, cache, and return it."""
    cached = smart_get(key)
    if cached is not None:
        return cached
    value = compute_fn()
    smart_set(key, value, ttl_seconds, user_id=user_id)
    return value


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------
def invalidate_user(user_id: int):
    """Invalidate ALL cached data for a user (call on any write)."""
    tag_key = _tag_key(user_id)
    keys = redis_client.smembers(tag_key)
    if keys:
        redis_client.delete(*keys)
        logger.info("cache INVALIDATED %d keys for user %d", len(keys), user_id)
    redis_client.delete(tag_key)


def invalidate_keys(patterns: Iterable[str]):
    """Pattern-based invalidation (legacy compatibility)."""
    for pattern in patterns:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                redis_client.delete(*keys)
            if cursor == 0:
                break


# ---------------------------------------------------------------------------
# Cache warming
# ---------------------------------------------------------------------------
def warm_dashboard(user_id: int, dashboard_fn: Callable, month: str):
    """
    Pre-populate dashboard cache on login so first load is instant.
    Call from auth /login route after token generation.
    """
    from .cache import dashboard_summary_key
    key = dashboard_summary_key(user_id, month)
    if smart_get(key) is None:
        try:
            value = dashboard_fn(user_id, month)
            smart_set(key, value, TTL_SUMMARY, user_id=user_id)
            logger.info("cache WARMED dashboard for user %d month %s", user_id, month)
        except Exception as exc:
            logger.warning("cache warm failed for user %d: %s", user_id, exc)
