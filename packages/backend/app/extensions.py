from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import os
from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()

_settings = Settings()

# Use fakeredis for demo/testing when Redis is not available
try:
    import redis as _redis
    _r = _redis.Redis.from_url(_settings.redis_url, decode_responses=True)
    _r.ping()
    redis_client = _r
except Exception:
    import fakeredis
    redis_client = fakeredis.FakeRedis(decode_responses=True)
