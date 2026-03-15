"""Smart caching strategy for dashboard and analytics.

Provides intelligent cache management with:
- Multi-layer caching (in-memory L1 + Redis L2)
- Smart cache invalidation on data mutations
- TTL-based expiration with configurable policies per data type
- Cache warming and preloading
- Cache statistics and monitoring
- Decorator-based caching for service functions
"""

import hashlib
import json
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Optional

from app.extensions import redis_client


# ─── Configuration ──────────────────────────────────────────────────

# TTL policies per data type (seconds)
CACHE_POLICIES = {
    "dashboard": {"ttl": 300, "prefix": "dash"},       # 5 min
    "analytics": {"ttl": 600, "prefix": "analytics"},   # 10 min
    "insights": {"ttl": 900, "prefix": "insights"},     # 15 min
    "categories": {"ttl": 3600, "prefix": "cat"},       # 1 hour
    "user_prefs": {"ttl": 7200, "prefix": "uprefs"},    # 2 hours
    "summary": {"ttl": 1800, "prefix": "summary"},      # 30 min
    "report": {"ttl": 3600, "prefix": "report"},        # 1 hour
    "default": {"ttl": 300, "prefix": "misc"},           # 5 min default
}


# ─── In-Memory L1 Cache ─────────────────────────────────────────────

class L1Cache:
    """Simple in-memory LRU-like cache as L1 layer.

    Fast local cache that sits in front of Redis.
    """

    def __init__(self, max_size: int = 1000):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from L1 cache."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        value, expires_at = entry
        if expires_at and time.time() > expires_at:
            del self._store[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in L1 cache."""
        if len(self._store) >= self._max_size:
            self._evict()
        expires_at = time.time() + ttl if ttl > 0 else 0
        self._store[key] = (value, expires_at)

    def delete(self, key: str):
        """Delete a specific key."""
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str):
        """Invalidate all keys matching a prefix."""
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]

    def clear(self):
        """Clear entire L1 cache."""
        self._store.clear()

    def stats(self) -> dict:
        """Get L1 cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0,
        }

    def _evict(self):
        """Evict expired entries, then oldest if needed."""
        now = time.time()
        # First pass: remove expired
        expired = [k for k, (v, exp) in self._store.items() if exp and now > exp]
        for k in expired:
            del self._store[k]

        # If still too big, remove oldest (first inserted)
        while len(self._store) >= self._max_size:
            oldest = next(iter(self._store))
            del self._store[oldest]


# Global L1 cache instance
_l1_cache = L1Cache()


# ─── Cache Key Generation ───────────────────────────────────────────


def _make_cache_key(prefix: str, user_id: int, params: dict | None = None) -> str:
    """Generate a deterministic cache key.

    Args:
        prefix: Cache namespace prefix
        user_id: User ID for isolation
        params: Optional query parameters

    Returns:
        Cache key string like "dash:user:1:abc123"
    """
    key = f"{prefix}:user:{user_id}"
    if params:
        # Sort params for deterministic keys
        param_str = json.dumps(params, sort_keys=True, default=str)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        key = f"{key}:{param_hash}"
    return key


# ─── Cache Operations ───────────────────────────────────────────────


def cache_get(key: str) -> Optional[Any]:
    """Get value from cache (L1 first, then L2/Redis).

    Returns:
        Cached value or None
    """
    # Try L1
    value = _l1_cache.get(key)
    if value is not None:
        return value

    # Try L2 (Redis)
    try:
        raw = redis_client.get(key)
        if raw:
            value = json.loads(raw)
            # Promote to L1
            ttl = redis_client.ttl(key)
            if ttl and ttl > 0:
                _l1_cache.set(key, value, min(ttl, 300))
            return value
    except Exception:
        pass

    return None


def cache_set(key: str, value: Any, ttl: int = 300):
    """Set value in both L1 and L2 cache.

    Args:
        key: Cache key
        value: Value to cache (must be JSON-serializable)
        ttl: Time to live in seconds
    """
    # Set in L1
    _l1_cache.set(key, value, min(ttl, 300))

    # Set in L2 (Redis)
    try:
        serialized = json.dumps(value, default=str)
        redis_client.setex(key, ttl, serialized)
    except Exception:
        pass  # Cache failures shouldn't break the app


def cache_delete(key: str):
    """Delete from both cache layers."""
    _l1_cache.delete(key)
    try:
        redis_client.delete(key)
    except Exception:
        pass


def cache_invalidate_user(user_id: int, data_types: list[str] | None = None):
    """Invalidate all cached data for a user.

    Args:
        user_id: User ID to invalidate
        data_types: Optional list of data types to invalidate.
                    If None, invalidates all.
    """
    types = data_types or list(CACHE_POLICIES.keys())

    for dtype in types:
        policy = CACHE_POLICIES.get(dtype, CACHE_POLICIES["default"])
        prefix = f"{policy['prefix']}:user:{user_id}"

        # Invalidate L1
        _l1_cache.invalidate_prefix(prefix)

        # Invalidate L2 (Redis) - scan for matching keys
        try:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor, match=f"{prefix}*", count=100)
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass


def cache_invalidate_all():
    """Clear entire cache (both layers)."""
    _l1_cache.clear()
    try:
        # Only clear our cache keys, not all Redis data
        for policy in CACHE_POLICIES.values():
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor, match=f"{policy['prefix']}:*", count=100)
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
    except Exception:
        pass


# ─── Cache Decorator ────────────────────────────────────────────────


def cached(data_type: str = "default", ttl: int | None = None,
           key_params: list[str] | None = None):
    """Decorator for caching function results.

    Usage:
        @cached(data_type="dashboard")
        def get_dashboard(user_id, **kwargs):
            ...

    The first positional argument must be user_id.

    Args:
        data_type: Type of data for TTL policy
        ttl: Override TTL (seconds); None uses policy default
        key_params: List of kwargs to include in cache key
    """
    policy = CACHE_POLICIES.get(data_type, CACHE_POLICIES["default"])
    cache_ttl = ttl if ttl is not None else policy["ttl"]
    prefix = policy["prefix"]

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(user_id, *args, **kwargs):
            # Build cache key
            params = {}
            if key_params:
                params = {k: kwargs.get(k) for k in key_params if k in kwargs}
            if args:
                params["_args"] = str(args)

            key = _make_cache_key(prefix, user_id, params or None)

            # Try cache
            result = cache_get(key)
            if result is not None:
                return result

            # Execute function
            result = func(user_id, *args, **kwargs)

            # Cache result
            if result is not None:
                cache_set(key, result, cache_ttl)

            return result

        wrapper._cache_prefix = prefix
        wrapper._cache_data_type = data_type
        return wrapper

    return decorator


# ─── Cache Warming ──────────────────────────────────────────────────


def warm_cache_for_user(user_id: int, warmers: dict[str, Callable] | None = None) -> dict:
    """Pre-populate cache for a user.

    Args:
        user_id: User ID to warm cache for
        warmers: Dict mapping data_type to callable(user_id)

    Returns:
        Dict of warmed data types and their status
    """
    results = {}

    if warmers:
        for data_type, func in warmers.items():
            try:
                result = func(user_id)
                if result is not None:
                    policy = CACHE_POLICIES.get(data_type, CACHE_POLICIES["default"])
                    key = _make_cache_key(policy["prefix"], user_id)
                    cache_set(key, result, policy["ttl"])
                    results[data_type] = {"status": "warmed", "key": key}
                else:
                    results[data_type] = {"status": "empty"}
            except Exception as e:
                results[data_type] = {"status": "error", "error": str(e)}

    return results


# ─── Statistics ─────────────────────────────────────────────────────


# In-memory stats tracking
_cache_stats = {
    "total_gets": 0,
    "total_sets": 0,
    "total_deletes": 0,
    "total_invalidations": 0,
    "started_at": None,
}


def get_cache_stats() -> dict:
    """Get comprehensive cache statistics."""
    l1_stats = _l1_cache.stats()

    # Redis stats
    l2_stats = {"connected": False, "keys": 0}
    try:
        redis_client.ping()
        l2_stats["connected"] = True
        # Count our cache keys
        total_keys = 0
        for policy in CACHE_POLICIES.values():
            cursor = 0
            count = 0
            while True:
                cursor, keys = redis_client.scan(cursor, match=f"{policy['prefix']}:*", count=100)
                count += len(keys)
                if cursor == 0:
                    break
            total_keys += count
        l2_stats["keys"] = total_keys
    except Exception:
        pass

    return {
        "l1_cache": l1_stats,
        "l2_cache": l2_stats,
        "policies": {
            name: {"ttl_seconds": p["ttl"], "prefix": p["prefix"]}
            for name, p in CACHE_POLICIES.items()
        },
    }


def reset_cache_stats():
    """Reset L1 cache statistics."""
    _l1_cache._hits = 0
    _l1_cache._misses = 0
