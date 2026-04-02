from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis


db = SQLAlchemy()
jwt = JWTManager()

# Lazy-initialized Redis client
_redis_client = None
_redis_url = None


def init_redis(redis_url: str):
    """Initialize Redis client with the given URL."""
    global _redis_client, _redis_url
    _redis_url = redis_url
    _redis_client = redis.Redis.from_url(redis_url, decode_responses=True)


def get_redis():
    """Get the Redis client, initializing with default if needed."""
    global _redis_client
    if _redis_client is None:
        from .config import Settings
        _settings = Settings()
        init_redis(_settings.redis_url)
    return _redis_client


# For backward compatibility, expose redis_client as a property-like getter
class RedisClientProxy:
    """Proxy that delegates to the actual Redis client."""
    def __getattr__(self, name):
        return getattr(get_redis(), name)


redis_client = RedisClientProxy()