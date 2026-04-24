import json
import logging
from typing import Iterable
from redis.exceptions import RedisError
from ..extensions import redis_client

logger = logging.getLogger("finmind.cache")


def monthly_summary_key(user_id: int, ym: str) -> str:
    return f"user:{user_id}:monthly_summary:{ym}"


def categories_key(user_id: int) -> str:
    return f"user:{user_id}:categories"


def upcoming_bills_key(user_id: int) -> str:
    return f"user:{user_id}:upcoming_bills"


def insights_key(user_id: int, ym: str) -> str:
    return f"insights:{user_id}:{ym}"


def dashboard_summary_key(user_id: int, ym: str) -> str:
    return f"user:{user_id}:dashboard_summary:{ym}"


def cache_set(key: str, value, ttl_seconds: int | None = None):
    payload = json.dumps(value)
    try:
        if ttl_seconds:
            redis_client.setex(key, ttl_seconds, payload)
        else:
            redis_client.set(key, payload)
    except RedisError as exc:
        logger.warning("Redis cache unavailable; skipping set for %s: %s", key, exc)


def cache_get(key: str):
    try:
        raw = redis_client.get(key)
    except RedisError as exc:
        logger.warning("Redis cache unavailable; cache miss for %s: %s", key, exc)
        return None
    return json.loads(raw) if raw else None


def cache_delete_patterns(patterns: Iterable[str]):
    for pattern in patterns:
        cursor = 0
        while True:
            try:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    redis_client.delete(*keys)
            except RedisError as exc:
                logger.warning("Redis cache unavailable; skipping delete for %s: %s", pattern, exc)
                break
            if cursor == 0:
                break
