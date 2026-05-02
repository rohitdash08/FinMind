import json
import logging
from typing import Iterable
from ..extensions import redis_client

logger = logging.getLogger("finmind.cache")


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
    if ttl_seconds:
        redis_client.setex(key, ttl_seconds, payload)
    else:
        redis_client.set(key, payload)


def cache_get(key: str):
    raw = redis_client.get(key)
    return json.loads(raw) if raw else None


def cache_delete_patterns(patterns: Iterable[str]):
    for pattern in patterns:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                redis_client.delete(*keys)
            if cursor == 0:
                break


def _calculate_hit_rate(info: dict) -> float:
    """Calculate cache hit rate from Redis info stats."""
    hits = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total = hits + misses
    if total == 0:
        return 0.0
    return round(hits / total, 4)


class CacheManager:
    """Smart cache manager with TTL strategies and invalidation."""

    # TTL strategies by data volatility
    TTL_STRATEGIES = {
        "realtime": 30,        # 30s - highly volatile (pending reminders)
        "short": 300,          # 5min - frequently changing (expenses, bills)
        "medium": 1800,        # 30min - moderately stable (dashboard, categories)
        "long": 3600,          # 1hr - stable (insights, summaries)
        "static": 86400,       # 24h - rarely changing (user profile)
    }

    def get_or_set(self, key: str, factory_fn, ttl_strategy: str = "medium"):
        """Get from cache or compute and cache with a TTL strategy.

        Args:
            key: Cache key.
            factory_fn: Callable that produces the value on cache miss.
            ttl_strategy: One of realtime/short/medium/long/static.

        Returns:
            Cached or freshly computed value.
        """
        try:
            cached = cache_get(key)
        except Exception:
            logger.warning("Cache get failed for key=%s", key, exc_info=True)
            cached = None
        if cached is not None:
            return cached

        value = factory_fn()
        ttl = self.TTL_STRATEGIES.get(ttl_strategy, 1800)
        try:
            cache_set(key, value, ttl)
        except Exception:
            logger.warning("Cache set failed for key=%s", key, exc_info=True)
        return value

    def invalidate_user(self, user_id: int):
        """Invalidate all caches for a user."""
        patterns = [
            f"user:{user_id}:*",
        ]
        try:
            cache_delete_patterns(patterns)
        except Exception:
            logger.warning(
                "Cache invalidation failed for user=%s", user_id, exc_info=True
            )

    def invalidate_user_type(self, user_id: int, cache_type: str):
        """Invalidate specific cache type for a user.

        Args:
            user_id: The user id.
            cache_type: The cache type prefix (e.g. dashboard_summary, monthly_summary).
        """
        pattern = f"user:{user_id}:{cache_type}:*"
        try:
            cache_delete_patterns([pattern])
        except Exception:
            logger.warning(
                "Cache type invalidation failed for user=%s type=%s",
                user_id,
                cache_type,
                exc_info=True,
            )

    def get_stats(self):
        """Get cache statistics.

        Returns:
            dict with hits, misses, hit_rate, memory_used, and keys count.
        """
        try:
            info = redis_client.info("stats")
            memory = redis_client.info("memory")
            return {
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": _calculate_hit_rate(info),
                "memory_used": memory.get("used_memory_human", "N/A"),
                "keys": redis_client.dbsize(),
            }
        except Exception:
            logger.warning("Failed to retrieve cache stats", exc_info=True)
            return {
                "hits": 0,
                "misses": 0,
                "hit_rate": 0.0,
                "memory_used": "N/A",
                "keys": 0,
                "error": "stats_unavailable",
            }


# Singleton instance
cache_manager = CacheManager()
