from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
import redis
from .config import Settings


db = SQLAlchemy()
jwt = JWTManager()

_settings = Settings()
redis_client = redis.Redis.from_url(_settings.redis_url, decode_responses=True)


def configure_redis(redis_url: str) -> None:
    redis_client.connection_pool.disconnect()
    redis_client.connection_pool = redis.ConnectionPool.from_url(
        redis_url,
        decode_responses=True,
    )
