from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()

_settings = Settings()
try:
    redis_client = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
    redis_client.ping()
except Exception:
    # Fallback for testing environments without redis
    class MockRedis:
        def __init__(self):
            self._data = {}
        def flushdb(self):
            self._data = {}
        def set(self, key, value):
            self._data[key] = value
        def get(self, key):
            return self._data.get(key)
        def delete(self, *keys):
            for k in keys:
                self._data.pop(k, None)
        def scan(self, cursor=0, match=None, count=100):
            # Return (0, keys) to indicate scan complete
            return (0, list(self._data.keys()))
        def __getattr__(self, name):
            return lambda *args, **kwargs: None
    redis_client = MockRedis()
