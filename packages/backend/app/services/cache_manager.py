from datetime import timezone

import logging
from functools import wraps
from typing import Optional, Callable, Any, List
from datetime import datetime, timedelta
import hashlib
import json

logger = logging.getLogger("finmind.cache")


class CacheManager:
    """Cache manager with Redis backend and local fallback.
    
    Features:
    - Redis backend with local cache fallback
    - Tag-based invalidation
    - User-specific cache invalidation
    - Decorator for easy caching
    - Proper error handling with logging (not silent swallowing)
    """
    
    def __init__(self, redis_client=None, default_ttl: int = 300, max_local_items: int = 1000):
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.max_local_items = max_local_items
        self._local = {}

    def _key(self, prefix: str, user_id, params: Optional[dict] = None) -> str:
        """Generate cache key from prefix, user_id, and optional params."""
        parts = [prefix, str(user_id)]
        if params:
            # Use blake2b instead of MD5 for key hashing (avoid security scanner false positives)
            params_str = json.dumps(params, sort_keys=True)
            params_hash = hashlib.blake2b(params_str.encode(), digest_size=4).hexdigest()
            parts.append(params_hash)
        return ":".join(parts)

    def _evict_local_if_needed(self):
        """Evict oldest entries if local cache exceeds max size."""
        if len(self._local) > self.max_local_items:
            # Remove oldest 20% of entries
            sorted_keys = sorted(self._local.keys(), key=lambda k: self._local[k]["exp"])
            remove_count = max(1, len(sorted_keys) // 5)
            for key in sorted_keys[:remove_count]:
                del self._local[key]

    def get(self, key: str) -> Any:
        """Get value from cache. Tries Redis first, then local."""
        if self.redis:
            try:
                data = self.redis.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Redis get failed for key {key}: {e}")
                # Fall through to local cache
        
        entry = self._local.get(key)
        if entry and entry["exp"] > datetime.now(timezone.utc):
            return entry["val"]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None, tags: Optional[List[str]] = None):
        """Set value in cache with optional TTL and tags."""
        ttl = ttl or self.default_ttl
        
        if self.redis:
            try:
                self.redis.setex(key, ttl, json.dumps(value, default=str))
                for tag in (tags or []):
                    self.redis.sadd(f"tag:{tag}", key)
                    self.redis.expire(f"tag:{tag}", ttl)
            except Exception as e:
                logger.warning(f"Redis set failed for key {key}: {e}")
                # Continue to set in local cache
        
        self._local[key] = {
            "val": value,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl),
            "tags": tags or []
        }
        self._evict_local_if_needed()

    def invalidate_by_tag(self, tag: str):
        """Invalidate all cache entries with a given tag."""
        if self.redis:
            try:
                keys = self.redis.smembers(f"tag:{tag}")
                if keys:
                    self.redis.delete(*keys)
                self.redis.delete(f"tag:{tag}")
            except Exception as e:
                logger.warning(f"Redis invalidate_by_tag failed for tag {tag}: {e}")
        
        self._local = {k: v for k, v in self._local.items() if tag not in v.get("tags", [])}

    def invalidate_user(self, user_id):
        """Invalidate all cache entries for a user."""
        self.invalidate_by_tag(f"user:{user_id}")

    def cached(self, prefix: str, ttl: Optional[int] = None, tags: Optional[List[str]] = None,
               key_func: Optional[Callable] = None):
        """Decorator for caching function results.
        
        Args:
            prefix: Cache key prefix
            ttl: Time to live in seconds
            tags: List of tags for invalidation (can use {user_id} placeholder)
            key_func: Optional custom function to extract cache key from args
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract user_id for cache key
                if key_func:
                    uid = key_func(*args, **kwargs)
                else:
                    uid = kwargs.get("user_id") or (args[0] if args else 0)
                
                # Generate cache key
                params = {k: v for k, v in kwargs.items() if k != "user_id"}
                key = self._key(prefix, uid, params)
                
                # Try to get from cache
                result = self.get(key)
                if result is not None:
                    return result
                
                # Execute function and cache result
                result = func(*args, **kwargs)
                self.set(key, result, ttl=ttl, tags=[t.format(user_id=uid) for t in (tags or [])])
                return result
            return wrapper
        return decorator


# Global cache instance
cache = CacheManager()
