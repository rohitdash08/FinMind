"""Event-driven financial activity system (issue #97)."""
import json, logging, time, uuid
from ..extensions import redis_client

logger = logging.getLogger("finmind.events")
STREAM_KEY = "events:stream"
CONSUMER_PREFIX = "events:consumer:"
TTL = 60 * 60 * 24 * 7  # 7 days

EVENT_TYPES = [
    "expense.created", "expense.updated", "expense.deleted",
    "bill.due_soon", "bill.paid", "budget.exceeded", "budget.warning",
    "savings_goal.milestone", "savings_goal.completed",
    "anomaly.detected", "subscription.price_increase",
]


def emit(event_type: str, user_id: int, payload: dict) -> str:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event type: {event_type}")
    event_id = str(uuid.uuid4())
    event = {"id": event_id, "type": event_type, "user_id": user_id,
             "payload": payload, "ts": time.time()}
    redis_client.rpush(f"{STREAM_KEY}:{user_id}", json.dumps(event))
    redis_client.expire(f"{STREAM_KEY}:{user_id}", TTL)
    logger.info("Event emitted: %s user=%d id=%s", event_type, user_id, event_id)
    return event_id


def get_events(user_id: int, limit: int = 50, event_type: str = None) -> list:
    raw = redis_client.lrange(f"{STREAM_KEY}:{user_id}", -limit, -1)
    events = [json.loads(r) for r in raw]
    if event_type:
        events = [e for e in events if e["type"] == event_type]
    return list(reversed(events))


def get_unread_count(user_id: int) -> int:
    cursor_key = f"{CONSUMER_PREFIX}{user_id}"
    cursor_raw = redis_client.get(cursor_key)
    cursor = int(cursor_raw) if cursor_raw else 0
    total = redis_client.llen(f"{STREAM_KEY}:{user_id}")
    return max(0, total - cursor)


def mark_read(user_id: int):
    total = redis_client.llen(f"{STREAM_KEY}:{user_id}")
    redis_client.setex(f"{CONSUMER_PREFIX}{user_id}", TTL, str(total))
