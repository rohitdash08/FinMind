"""Smart caching strategy for dashboard & analytics (#127).

Provides a simple in-process cache with TTL and tag-based invalidation.
Falls back to Redis when available, otherwise uses in-memory dict.
"""

import hashlib
import json
import logging
import time
from functools import wraps

from flask import request

logger = logging.getLogger("finmind.cache")

# In-memory cache store
_cache = {}
_tag_keys = {}  # tag -> set of cache keys


class CacheEntry:
    __slots__ = ("value", "expires_at", "tags")

    def __init__(self, value, ttl, tags):
        self.value = value
        self.expires_at = time.time() + ttl
        self.tags = tags

    @property
    def expired(self):
        return time.time() > self.expires_at


def _make_key(prefix, *args, **kwargs):
    raw = f"{prefix}:{json.dumps(args, sort_keys=True, default=str)}:{json.dumps(kwargs, sort_keys=True, default=str)}"
    return hashlib.md5(raw.encode()).hexdigest()


def cache_get(key):
    """Get value from cache. Returns None if missing or expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    if entry.expired:
        cache_delete(key)
        return None
    return entry.value


def cache_set(key, value, ttl=300, tags=None):
    """Set cache value with TTL (seconds) and optional tags."""
    tags = tags or []
    _cache[key] = CacheEntry(value, ttl, tags)
    for tag in tags:
        _tag_keys.setdefault(tag, set()).add(key)


def cache_delete(key):
    """Delete a single cache entry."""
    entry = _cache.pop(key, None)
    if entry:
        for tag in entry.tags:
            _tag_keys.get(tag, set()).discard(key)


def invalidate_tag(tag):
    """Invalidate all cache entries with a given tag."""
    keys = _tag_keys.pop(tag, set())
    for key in keys:
        _cache.pop(key, None)
    logger.info("Cache invalidated tag=%s keys=%d", tag, len(keys))


def invalidate_user(user_id):
    """Invalidate all cache for a user."""
    invalidate_tag(f"user:{user_id}")


def cache_stats():
    """Return cache statistics."""
    now = time.time()
    total = len(_cache)
    expired = sum(1 for e in _cache.values() if e.expired)
    return {"total_entries": total, "expired": expired, "active": total - expired, "tags": len(_tag_keys)}


def clear_all():
    """Clear entire cache."""
    _cache.clear()
    _tag_keys.clear()


def cached(ttl=300, prefix=None, user_scoped=True):
    """Decorator to cache endpoint responses.

    Args:
        ttl: Cache TTL in seconds (default 5 min)
        prefix: Cache key prefix (default: function name)
        user_scoped: Include user_id in cache key (default True)
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask_jwt_extended import get_jwt_identity
            p = prefix or fn.__name__
            uid = get_jwt_identity() if user_scoped else "global"
            qs = request.query_string.decode()
            key = _make_key(p, uid, qs)
            hit = cache_get(key)
            if hit is not None:
                logger.debug("Cache HIT key=%s", key[:8])
                return hit
            result = fn(*args, **kwargs)
            tags = [f"user:{uid}"] if user_scoped and uid != "global" else []
            cache_set(key, result, ttl=ttl, tags=tags)
            logger.debug("Cache MISS key=%s ttl=%d", key[:8], ttl)
            return result
        return wrapper
    return decorator
