from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()

_settings = Settings()
redis_client = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
