"""
Reminder reliability tracking & delivery metrics (issue #123).
Tracks whether reminders were delivered, acknowledged, and measures success rates.
"""
import json, logging
from datetime import datetime, timezone
from ..extensions import redis_client

logger = logging.getLogger("finmind.reminders")

PREFIX = "reminder:track:"
STATS_KEY = "reminder:stats"
TTL = 60 * 60 * 24 * 30  # 30 days


def _utcnow(): return datetime.now(timezone.utc).isoformat()
def _key(reminder_id: int): return f"{PREFIX}{reminder_id}"


def record_sent(reminder_id: int, channel: str, user_id: int):
    rec = {"reminder_id": reminder_id, "user_id": user_id, "channel": channel,
           "sent_at": _utcnow(), "status": "sent", "ack_at": None}
    redis_client.setex(_key(reminder_id), TTL, json.dumps(rec))
    _incr_stat("sent")
    logger.info("Reminder %d sent via %s to user %d", reminder_id, channel, user_id)


def record_delivered(reminder_id: int):
    raw = redis_client.get(_key(reminder_id))
    if not raw: return
    rec = json.loads(raw); rec["status"] = "delivered"; rec["delivered_at"] = _utcnow()
    redis_client.setex(_key(reminder_id), TTL, json.dumps(rec))
    _incr_stat("delivered")


def record_acknowledged(reminder_id: int):
    raw = redis_client.get(_key(reminder_id))
    if not raw: return
    rec = json.loads(raw); rec["status"] = "acknowledged"; rec["ack_at"] = _utcnow()
    redis_client.setex(_key(reminder_id), TTL, json.dumps(rec))
    _incr_stat("acknowledged")


def get_status(reminder_id: int) -> dict | None:
    raw = redis_client.get(_key(reminder_id))
    return json.loads(raw) if raw else None


def get_metrics() -> dict:
    raw = redis_client.hgetall(STATS_KEY)
    stats = {k.decode() if isinstance(k, bytes) else k:
             int(v) for k, v in raw.items()}
    sent = stats.get("sent", 0)
    delivered = stats.get("delivered", 0)
    acked = stats.get("acknowledged", 0)
    return {
        "total_sent": sent,
        "total_delivered": delivered,
        "total_acknowledged": acked,
        "delivery_rate_pct": round(delivered / sent * 100, 1) if sent else 0,
        "acknowledgment_rate_pct": round(acked / sent * 100, 1) if sent else 0,
    }


def _incr_stat(field: str):
    redis_client.hincrby(STATS_KEY, field, 1)
