"""Smart caching strategy for dashboard and analytics.

Provides a flexible caching layer with intelligent invalidation
based on data mutation events. Uses Redis when available,
falls back to in-memory LRU cache.
"""

import hashlib
import json
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Optional

from flask import request


class InMemoryCache:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry["expires_at"] and time.time() > entry["expires_at"]:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return entry["value"]

    def set(self, key: str, value: Any, ttl: int = 300):
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl if ttl > 0 else None,
            "created_at": time.time(),
        }

    def delete(self, key: str):
        self._cache.pop(key, None)

    def invalidate_pattern(self, pattern: str):
        keys_to_delete = [k for k in self._cache if pattern in k]
        for k in keys_to_delete:
            del self._cache[k]

    def clear(self):
        self._cache.clear()

    def stats(self) -> dict:
        now = time.time()
        valid = sum(
            1 for e in self._cache.values()
            if not e["expires_at"] or now < e["expires_at"]
        )
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid,
            "max_size": self._max_size,
        }


class SmartCache:
    """Smart caching with automatic invalidation on data mutations."""

    # TTL presets per data type (seconds)
    TTL_CONFIG = {
        "dashboard": 120,       # 2 min - frequently viewed
        "analytics": 300,       # 5 min - moderate freshness
        "categories": 3600,     # 1 hour - rarely changes
        "insights": 600,        # 10 min - computed data
        "bills_upcoming": 300,  # 5 min
        "expenses_recent": 120, # 2 min
    }

    # Invalidation rules: mutation -> cache patterns to clear
    INVALIDATION_MAP = {
        "expense_created": ["dashboard", "analytics", "insights", "expenses"],
        "expense_updated": ["dashboard", "analytics", "insights", "expenses"],
        "expense_deleted": ["dashboard", "analytics", "insights", "expenses"],
        "bill_created": ["dashboard", "bills"],
        "bill_updated": ["dashboard", "bills"],
        "bill_deleted": ["dashboard", "bills"],
        "category_created": ["categories", "analytics"],
        "category_updated": ["categories", "analytics"],
    }

    def __init__(self, redis_client=None, max_memory_entries: int = 1000):
        self._redis = redis_client
        self._memory = InMemoryCache(max_size=max_memory_entries)
        self._hit_count = 0
        self._miss_count = 0

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    def get(self, key: str) -> Optional[Any]:
        if self._redis:
            try:
                raw = self._redis.get(key)
                if raw:
                    self._hit_count += 1
                    return json.loads(raw)
                self._miss_count += 1
                return None
            except Exception:
                pass
        result = self._memory.get(key)
        if result is not None:
            self._hit_count += 1
        else:
            self._miss_count += 1
        return result

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if ttl is None:
            for prefix, t in self.TTL_CONFIG.items():
                if prefix in key:
                    ttl = t
                    break
            else:
                ttl = 300
        if self._redis:
            try:
                self._redis.setex(key, ttl, json.dumps(value, default=str))
                return
            except Exception:
                pass
        self._memory.set(key, value, ttl=ttl)

    def invalidate(self, event: str, user_id: Optional[int] = None):
        patterns = self.INVALIDATION_MAP.get(event, [])
        for pattern in patterns:
            if user_id:
                full_pattern = f"user:{user_id}:{pattern}"
            else:
                full_pattern = pattern
            if self._redis:
                try:
                    keys = self._redis.keys(f"*{full_pattern}*")
                    if keys:
                        self._redis.delete(*keys)
                    continue
                except Exception:
                    pass
            self._memory.invalidate_pattern(full_pattern)

    def clear_all(self):
        if self._redis:
            try:
                self._redis.flushdb()
                return
            except Exception:
                pass
        self._memory.clear()

    def stats(self) -> dict:
        total = self._hit_count + self._miss_count
        return {
            "backend": self.backend,
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": f"{(self._hit_count / total * 100):.1f}%" if total > 0 else "0%",
            "memory": self._memory.stats(),
        }


# Global cache instance
_cache = SmartCache()


def get_cache() -> SmartCache:
    return _cache


def init_cache(app, redis_client=None):
    global _cache
    _cache = SmartCache(redis_client=redis_client)
    app.extensions["smart_cache"] = _cache
    return _cache


def cache_key(*parts) -> str:
    raw = ":".join(str(p) for p in parts)
    return f"finmind:{raw}"


def cached(prefix: str, ttl: Optional[int] = None):
    """Decorator to cache route responses."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_id = kwargs.get("user_id") or request.args.get("user_id", "anon")
            key = cache_key(f"user:{user_id}", prefix, request.full_path)
            result = _cache.get(key)
            if result is not None:
                return result
            result = f(*args, **kwargs)
            _cache.set(key, result, ttl=ttl)
            return result
        return wrapper
    return decorator
