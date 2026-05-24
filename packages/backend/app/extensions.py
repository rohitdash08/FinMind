"""
FinMind — Flask extensions

Add cache and limiter here so the route can import them cleanly.
Requires:
    pip install Flask-Caching Flask-Limiter redis
"""

from flask_caching import Cache
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
jwt = JWTManager()

# Fix #9 — rate limiting (storage_uri → Redis in production)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",        # swap to "redis://localhost:6379/0" in prod
)

# Fix #9 — response cache (CACHE_TYPE configured in app config)
cache = Cache()


def init_extensions(app):
    db.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)
    cache.init_app(app, config={
        "CACHE_TYPE": "SimpleCache",        # swap to RedisCache in prod
        "CACHE_DEFAULT_TIMEOUT": 3600,
    })
