"""In-memory caching layer using Flask-Caching SimpleCache (Issue #127).

Provides smart caching for dashboard and analytics queries with:
- TTL of 5 minutes for dashboard queries
- TTL of 15 minutes for analytics queries
- Cache key based on user_id + query params
- Invalidation on expense/bill/category CRUD operations
"""

import hashlib
import logging
from functools import wraps
from typing import Callable

from flask import request, g
from flask_caching import Cache

logger = logging.getLogger("finmind.memory_cache")

# The Cache instance; initialized during app creation via init_memory_cache()
memory_cache = Cache()

DASHBOARD_TTL = 300   # 5 minutes
ANALYTICS_TTL = 900   # 15 minutes


def init_memory_cache(app):
    """Initialize the in-memory cache on the Flask app."""
    app.config.setdefault("CACHE_TYPE", "SimpleCache")
    app.config.setdefault("CACHE_DEFAULT_TIMEOUT", DASHBOARD_TTL)
    memory_cache.init_app(app)
    logger.info("In-memory cache initialized (SimpleCache)")


def _build_cache_key(prefix: str, user_id: int) -> str:
    """Build a deterministic cache key from prefix, user_id and query params."""
    params = sorted(request.args.items())
    raw = f"{prefix}:{user_id}:{params}"
    h = hashlib.md5(raw.encode()).hexdigest()[:16]
    return f"{prefix}:{user_id}:{h}"


def cached_endpoint(prefix: str, ttl: int) -> Callable:
    """Decorator for caching JWT-protected endpoint responses.

    Sets g.cache_hit so the after_request hook can add the X-Cache-Hit header.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask_jwt_extended import get_jwt_identity
            uid = int(get_jwt_identity())
            key = _build_cache_key(prefix, uid)
            cached = memory_cache.get(key)
            if cached is not None:
                g.cache_hit = True
                logger.debug("Cache HIT key=%s", key)
                return cached
            g.cache_hit = False
            result = fn(*args, **kwargs)
            memory_cache.set(key, result, timeout=ttl)
            logger.debug("Cache MISS key=%s ttl=%s", key, ttl)
            return result
        return wrapper
    return decorator


def invalidate_user_cache(user_id: int) -> None:
    """Invalidate all in-memory cached entries for a user.

    Since SimpleCache doesn't support pattern-based deletion, we clear
    the entire cache. For production at scale, a tagged cache backend
    (e.g. Redis) would be more appropriate.
    """
    memory_cache.clear()
    logger.info("In-memory cache cleared for user=%s (full clear)", user_id)
