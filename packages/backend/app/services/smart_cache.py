"""Smart caching service with intelligent invalidation for FinMind.

Provides cache-aside pattern with:
- Tag-based cache invalidation
- Automatic TTL based on data freshness requirements
- Cache hit/miss metrics
- Dashboard and analytics specific caching strategies
"""

import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from functools import wraps

from ..extensions import redis_client

logger = logging.getLogger("finmind.cache")

# Cache key prefixes
CACHE_PREFIX = "finmind:cache:"
METRICS_PREFIX = "finmind:cache:metrics:"
TAG_PREFIX = "finmind:cache:tag:"

# TTL presets (seconds)
TTL_PRESETS = {
    "realtime": 30,       # 30 seconds - dashboard live data
    "frequent": 300,      # 5 minutes - recent transactions
    "standard": 900,      # 15 minutes - analytics
    "daily": 86400,       # 1 day - historical reports
    "weekly": 604800,     # 1 week - aggregated stats
}


class SmartCache:
    """Intelligent cache with tag-based invalidation."""

    def __init__(self, redis=None):
        self.redis = redis or redis_client

    def _make_key(self, namespace: str, key: str) -> str:
        return f"{CACHE_PREFIX}{namespace}:{key}"

    def _make_tag_key(self, tag: str) -> str:
        return f"{TAG_PREFIX}{tag}"

    def _make_metric_key(self, namespace: str) -> str:
        return f"{METRICS_PREFIX}{namespace}"

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """Retrieve cached value. Returns None on miss."""
        cache_key = self._make_key(namespace, key)
        raw = self.redis.get(cache_key)
        if raw is None:
            self._record_miss(namespace)
            return None
        self._record_hit(namespace)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: str = "standard",
        tags: list[str] | None = None,
    ) -> bool:
        """Store value with TTL and optional tags for invalidation."""
        cache_key = self._make_key(namespace, key)
        ttl_seconds = TTL_PRESETS.get(ttl, 900)

        serialized = json.dumps(value, default=str)
        pipe = self.redis.pipeline()
        pipe.setex(cache_key, ttl_seconds, serialized)

        # Register under tags for bulk invalidation
        if tags:
            for tag in tags:
                tag_key = self._make_tag_key(tag)
                pipe.sadd(tag_key, cache_key)
                pipe.expire(tag_key, ttl_seconds + 60)  # Tag lives slightly longer
            pipe.execute()
        else:
            pipe.execute()

        return True

    def delete(self, namespace: str, key: str) -> bool:
        """Delete a specific cache entry."""
        cache_key = self._make_key(namespace, key)
        return bool(self.redis.delete(cache_key))

    def invalidate_tag(self, tag: str) -> int:
        """Invalidate all cache entries associated with a tag."""
        tag_key = self._make_tag_key(tag)
        keys = self.redis.smembers(tag_key)
        if not keys:
            return 0
        deleted = self.redis.delete(*list(keys))
        self.redis.delete(tag_key)
        logger.info("Invalidated tag=%s keys=%d", tag, deleted)
        return deleted

    def invalidate_namespace(self, namespace: str) -> int:
        """Invalidate all entries in a namespace using SCAN."""
        pattern = self._make_key(namespace, "*")
        keys = list(self.redis.scan_iter(pattern))
        if not keys:
            return 0
        deleted = self.redis.delete(*keys)
        logger.info("Invalidated namespace=%s keys=%d", namespace, deleted)
        return deleted

    def get_or_set(
        self,
        namespace: str,
        key: str,
        factory: callable,
        ttl: str = "standard",
        tags: list[str] | None = None,
    ) -> Any:
        """Cache-aside pattern: get from cache, or compute and store."""
        cached = self.get(namespace, key)
        if cached is not None:
            return cached
        value = factory()
        self.set(namespace, key, value, ttl=ttl, tags=tags)
        return value

    # ---- Metrics ----

    def _record_hit(self, namespace: str):
        key = self._make_metric_key(namespace)
        pipe = self.redis.pipeline()
        pipe.hincrby(key, "hits", 1)
        pipe.hincrby(key, "total", 1)
        pipe.expire(key, 86400)
        pipe.execute()

    def _record_miss(self, namespace: str):
        key = self._make_metric_key(namespace)
        pipe = self.redis.pipeline()
        pipe.hincrby(key, "misses", 1)
        pipe.hincrby(key, "total", 1)
        pipe.expire(key, 86400)
        pipe.execute()

    def get_metrics(self, namespace: str) -> dict:
        """Get cache performance metrics for a namespace."""
        key = self._make_metric_key(namespace)
        data = self.redis.hgetall(key)
        if not data:
            return {"namespace": namespace, "hits": 0, "misses": 0, "hit_rate": 0}
        hits = int(data.get(b"hits", data.get("hits", 0)))
        misses = int(data.get(b"misses", data.get("misses", 0)))
        total = hits + misses
        return {
            "namespace": namespace,
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate": round(hits / max(total, 1), 4),
        }


# Singleton instance
cache = SmartCache()


def cached(namespace: str, ttl: str = "standard", tags: list[str] | None = None):
    """Decorator for caching function results.

    Usage:
        @cached("dashboard", ttl="frequent", tags=["expenses", "user:{uid}"])
        def get_dashboard_data(user_id):
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Build cache key from function name + args
            key_parts = [fn.__name__] + [str(a) for a in args[1:]] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()

            return cache.get_or_set(namespace, cache_key, lambda: fn(*args, **kwargs), ttl=ttl, tags=tags)
        return wrapper
    return decorator
