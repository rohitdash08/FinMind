from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
import os
import fakeredis
from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()

_settings = Settings()
if os.environ.get("FLASK_ENV") == "testing":
    redis_client = fakeredis.FakeRedis(decode_responses=True)
else:
    redis_client = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
