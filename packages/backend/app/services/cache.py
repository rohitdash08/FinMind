import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable

from ..extensions import redis_client

logger = logging.getLogger("finmind.cache")

DEFAULT_TTL = 300
DASHBOARD_TTL = 300
CATEGORIES_TTL = 600
BILLS_TTL = 600
INSIGHTS_TTL = 900

LOCK_TTL = 10
WARM_KEYS_PATTERNS = [
    "user:*:dashboard_summary:*",
    "user:*:categories",
    "user:*:upcoming_bills",
]


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    invalidations: int = 0
    warming_calls: int = 0

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total > 0 else 0.0


_stats = CacheStats()


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
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL
    redis_client.setex(key, ttl, payload)
    _stats.sets += 1


def cache_get(key: str):
    raw = redis_client.get(key)
    if raw:
        _stats.hits += 1
        return json.loads(raw)
    _stats.misses += 1
    return None


def cache_delete_patterns(patterns: Iterable[str]):
    for pattern in patterns:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                redis_client.delete(*keys)
                _stats.invalidations += len(keys)
            if cursor == 0:
                break


def cache_delete(key: str):
    redis_client.delete(key)
    _stats.invalidations += 1


def acquire_lock(lock_key: str, ttl: int = LOCK_TTL) -> bool:
    return bool(redis_client.set(lock_key, "1", nx=True, ex=ttl))


def release_lock(lock_key: str):
    redis_client.delete(lock_key)


def cache_aside(
    key: str,
    fetch_fn: Callable[[], Any],
    ttl_seconds: int | None = None,
    enable_lock: bool = True,
) -> Any:
    cached = cache_get(key)
    if cached is not None:
        return cached

    lock_key = f"lock:{key}"
    if enable_lock and not acquire_lock(lock_key):
        for _ in range(20):
            time.sleep(0.05)
            cached = cache_get(key)
            if cached is not None:
                return cached
        lock_key = None

    try:
        value = fetch_fn()
        cache_set(key, value, ttl_seconds)
        return value
    finally:
        if lock_key:
            release_lock(lock_key)


def clear_stats():
    _stats.hits = 0
    _stats.misses = 0
    _stats.sets = 0
    _stats.invalidations = 0
    _stats.warming_calls = 0


def get_stats() -> dict:
    return {
        "hits": _stats.hits,
        "misses": _stats.misses,
        "hit_rate": _stats.hit_rate(),
        "sets": _stats.sets,
        "invalidations": _stats.invalidations,
        "warming_calls": _stats.warming_calls,
    }


def warm_user_cache(user_id: int):
    today = date.today()
    ym = today.strftime("%Y-%m")
    _stats.warming_calls += 1

    from ..routes.dashboard import _compute_dashboard_summary

    summary = _compute_dashboard_summary(user_id, ym)
    cache_set(dashboard_summary_key(user_id, ym), summary, DASHBOARD_TTL)

    from ..routes.categories import _fetch_categories

    cats = _fetch_categories(user_id)
    cache_set(categories_key(user_id), cats, CATEGORIES_TTL)

    from ..routes.bills import _fetch_upcoming_bills

    bills = _fetch_upcoming_bills(user_id)
    cache_set(upcoming_bills_key(user_id), bills, BILLS_TTL)

    logger.info("Warmed cache for user_id=%s", user_id)
