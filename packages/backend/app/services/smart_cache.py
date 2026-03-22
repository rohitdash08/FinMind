"""Smart caching strategy with intelligent invalidation for FinMind.

Provides:
- Decorator-based route caching with per-entity TTLs
- Automatic cache invalidation on write operations
- Cache warming on user login
- Cache statistics and monitoring
- Entity-aware invalidation graph (changing expenses invalidates dashboard + analytics)
"""

import functools
import hashlib
import json
import time
from typing import Callable, Iterable

from flask import request
from flask_jwt_extended import get_jwt_identity

from ..extensions import redis_client

# TTL policies per entity type (seconds)
CACHE_TTL = {
    "dashboard": 300,      # 5 min — frequently viewed, moderate staleness OK
    "expenses": 120,       # 2 min — users expect near-real-time after adding
    "categories": 3600,    # 1 hour — rarely changes
    "bills": 600,          # 10 min — changes infrequently
    "insights": 900,       # 15 min — computed metrics, expensive queries
    "analytics": 600,      # 10 min
    "reminders": 1800,     # 30 min
}

# Invalidation graph: when entity X changes, also invalidate these
INVALIDATION_DEPS = {
    "expenses": ["dashboard", "insights", "analytics"],
    "categories": ["dashboard", "insights", "analytics", "expenses"],
    "bills": ["dashboard"],
    "reminders": [],
}

# Stats keys
STATS_PREFIX = "cache:stats"


def _cache_key(entity: str, user_id: int, suffix: str = "") -> str:
    """Build a namespaced cache key."""
    base = f"smart:{entity}:{user_id}"
    if suffix:
        base += f":{suffix}"
    return base


def _request_fingerprint() -> str:
    """Hash query params + path for unique cache key per request variant."""
    parts = request.path + "?" + request.query_string.decode("utf-8", errors="replace")
    return hashlib.md5(parts.encode()).hexdigest()[:12]


def _incr_stat(stat_type: str, entity: str):
    """Increment a cache stat counter."""
    key = f"{STATS_PREFIX}:{stat_type}:{entity}"
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 86400)  # stats expire after 24h
    pipe.execute()


def cached_route(entity: str, ttl: int | None = None):
    """Decorator for caching Flask route responses.

    Usage:
        @bp.get("/summary")
        @jwt_required()
        @cached_route("dashboard")
        def dashboard_summary():
            ...
    """
    effective_ttl = ttl or CACHE_TTL.get(entity, 300)

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            uid = int(get_jwt_identity())
            fingerprint = _request_fingerprint()
            key = _cache_key(entity, uid, fingerprint)

            # Try cache first
            raw = redis_client.get(key)
            if raw is not None:
                _incr_stat("hit", entity)
                return json.loads(raw), 200

            _incr_stat("miss", entity)

            # Execute the actual handler
            result = fn(*args, **kwargs)

            # Handle tuple returns (response, status_code)
            if isinstance(result, tuple):
                response_data, status_code = result[0], result[1]
                if status_code == 200:
                    _store(key, response_data, effective_ttl)
                return result

            # Store successful responses
            _store(key, result, effective_ttl)
            return result

        return wrapper
    return decorator


def _store(key: str, data, ttl: int):
    """Store data in cache with TTL."""
    try:
        payload = json.dumps(data) if not isinstance(data, str) else data
        redis_client.setex(key, ttl, payload)
    except (TypeError, ValueError):
        pass  # skip non-serializable responses


def invalidate_entity(entity: str, user_id: int):
    """Invalidate all caches for an entity and its dependents.

    Call this after any write operation (create, update, delete).

    Usage:
        invalidate_entity("expenses", user_id)
        # Also invalidates dashboard, insights, analytics
    """
    entities_to_clear = [entity] + INVALIDATION_DEPS.get(entity, [])
    patterns = [f"smart:{e}:{user_id}:*" for e in entities_to_clear]

    pipe = redis_client.pipeline()
    for pattern in patterns:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                pipe.delete(*keys)
            if cursor == 0:
                break

    # Track invalidation count
    for e in entities_to_clear:
        _incr_stat("invalidation", e)

    pipe.execute()


def warm_cache(user_id: int, warm_fns: dict[str, Callable] | None = None):
    """Pre-populate caches for a user (call on login).

    Args:
        user_id: The user ID to warm caches for.
        warm_fns: Optional dict of entity -> callable that returns data.
                  If not provided, only marks the warm timestamp.
    """
    redis_client.setex(f"cache:warmed:{user_id}", 3600, str(int(time.time())))

    if warm_fns:
        for entity, fn in warm_fns.items():
            try:
                data = fn()
                ttl = CACHE_TTL.get(entity, 300)
                key = _cache_key(entity, user_id, "default")
                _store(key, data, ttl)
            except Exception:
                continue  # best effort


def get_cache_stats(user_id: int | None = None) -> dict:
    """Get cache statistics.

    Returns hit/miss/invalidation counts per entity.
    """
    stats: dict = {}
    for stat_type in ("hit", "miss", "invalidation"):
        pattern = f"{STATS_PREFIX}:{stat_type}:*"
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                entity = key.split(":")[-1]
                if entity not in stats:
                    stats[entity] = {"hits": 0, "misses": 0, "invalidations": 0}
                val = int(redis_client.get(key) or 0)
                stats[entity][f"{stat_type}s" if stat_type != "invalidation" else "invalidations"] = val
            if cursor == 0:
                break

    # Compute hit rates
    for entity, data in stats.items():
        total = data["hits"] + data["misses"]
        data["hit_rate"] = round(data["hits"] / total * 100, 1) if total > 0 else 0.0

    return stats


def clear_user_cache(user_id: int):
    """Clear all caches for a user."""
    pattern = f"smart:*:{user_id}:*"
    cursor = 0
    while True:
        cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=200)
        if keys:
            redis_client.delete(*keys)
        if cursor == 0:
            break
