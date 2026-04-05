"""Smart reminder timing optimization (issue #111)."""
import json, logging
from datetime import datetime, timezone, time
from ..extensions import redis_client

logger = logging.getLogger("finmind.reminder_timing")
PREFIX = "remindertiming:"
TTL = 60 * 60 * 24 * 90


def _key(user_id): return f"{PREFIX}{user_id}"
def _utcnow(): return datetime.now(timezone.utc)


def record_engagement(user_id: int, hour: int, day_of_week: int):
    """Record that a user was active at this hour/day."""
    store = _load(user_id)
    slot = f"{day_of_week}:{hour}"
    store[slot] = store.get(slot, 0) + 1
    _save(user_id, store)


def get_optimal_time(user_id: int) -> dict:
    """Return the best hour + day to send reminders based on engagement history."""
    store = _load(user_id)
    if not store:
        return {"hour": 9, "day_of_week": None, "confidence": "low",
                "reason": "No engagement data — defaulting to 9AM"}
    best_slot = max(store, key=store.get)
    day, hour = map(int, best_slot.split(":"))
    total = sum(store.values())
    best_count = store[best_slot]
    confidence = "high" if best_count / total > 0.3 else "medium" if best_count / total > 0.1 else "low"
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    return {"hour": hour, "day_of_week": day, "day_name": days[day],
            "confidence": confidence, "engagement_count": best_count,
            "reason": f"Most active at {hour:02d}:00 on {days[day]} ({best_count}/{total} sessions)"}


def _load(user_id):
    raw = redis_client.get(_key(user_id))
    return json.loads(raw) if raw else {}

def _save(user_id, store):
    redis_client.setex(_key(user_id), TTL, json.dumps(store))
