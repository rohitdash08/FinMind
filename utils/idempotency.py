import redis
import os

redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
client = redis.from_url(redis_url)

def is_processed(idempotency_key: str) -> bool:
    """Check if a task with the given idempotency key was already processed."""
    return client.get(f"task_idemp_{idempotency_key}") is not None

def mark_processed(idempotency_key: str, ttl: int = 86400):
    """Mark a task as processed using the idempotency key with a TTL."""
    client.setex(f"task_idemp_{idempotency_key}", ttl, "true")