from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
import os
from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()

_settings = Settings()

if os.environ.get("FLASK_ENV") == "testing":
    class MockRedis:
        def get(self, *a, **kw): return None
        def set(self, *a, **kw): return True
        def setex(self, *a, **kw): return True
        def delete(self, *a, **kw): return 0
        def flushdb(self, *a, **kw): return True
        def ping(self, *a, **kw): return True
        def scan(self, cursor=0, match=None, count=None): return 0, []

    redis_client = MockRedis()
else:
    redis_client = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
