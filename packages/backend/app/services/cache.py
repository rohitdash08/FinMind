"""Smart caching strategy with intelligent invalidation."""

import json
import hashlib
from functools import wraps
from typing import Callable

from flask import request
from ..extensions import redis_client
import logging

logger = logging.getLogger("finmind.cache")

DEFAULT_TTL = 300  # 5 minutes


def cache_key(prefix: str, user_id: int, **kwargs) -> str:
    """Generate a deterministic cache key."""
    parts = f"{prefix}:{user_id}"
    if kwargs:
        param_hash = hashlib.md5(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:8]
        parts += f":{param_hash}"
    return parts


def cached(prefix: str, ttl: int = DEFAULT_TTL):
    """Decorator to cache endpoint responses in Redis.

    Automatically invalidates when user data changes.
    """
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask_jwt_extended import get_jwt_identity
            uid = get_jwt_identity()
            if not uid:
                return fn(*args, **kwargs)

            # Build cache key from request params
            params = dict(request.args)
            key = cache_key(prefix, uid, **params)

            # Try cache hit
            cached_data = redis_client.get(key)
            if cached_data:
                logger.debug("Cache HIT: %s", key)
                from flask import Response
                return Response(cached_data, content_type="application/json")

            # Cache miss - execute and store
            response = fn(*args, **kwargs)
            if response.status_code == 200:
                redis_client.setex(key, ttl, response.get_data(as_text=True))
                logger.debug("Cache SET: %s ttl=%d", key, ttl)

            return response
        return wrapper
    return decorator


def invalidate_user_cache(user_id: int, prefixes: list[str] | None = None):
    """Invalidate cache entries for a user.

    Args:
        user_id: The user whose cache to invalidate.
        prefixes: Specific cache prefixes to invalidate. If None, invalidates all.
    """
    if prefixes is None:
        prefixes = ["dashboard", "expenses", "bills", "insights", "digest"]

    for prefix in prefixes:
        pattern = f"{prefix}:{user_id}:*"
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info("Cache invalidated: %s (%d keys)", pattern, len(keys))

    # Also invalidate exact keys without params
    for prefix in prefixes:
        key = f"{prefix}:{user_id}"
        redis_client.delete(key)
