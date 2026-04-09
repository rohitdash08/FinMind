import json
from typing import Iterable
from ..extensions import redis_client


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
    if ttl_seconds:
        redis_client.setex(key, ttl_seconds, payload)
    else:
        redis_client.set(key, payload)


def cache_get(key: str):
    raw = redis_client.get(key)
    return json.loads(raw) if raw else None


def cache_delete_patterns(patterns: Iterable[str]):
    """
    Deletes all keys matching the given patterns from Redis.
    """
    pipe = redis_client.pipeline()
    for pattern in patterns:
        # Use SCAN to avoid blocking Redis for large key sets
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=1000) # Increased count for efficiency
            if keys:
                pipe.delete(*keys)
            if cursor == 0:
                break
    pipe.execute()
