"""Reminder reliability tracking & delivery metrics."""

from datetime import datetime, timedelta

from ..extensions import db, redis_client
from ..models import Reminder
import json
import logging

logger = logging.getLogger("finmind.reminder_tracking")

METRICS_KEY = "reminder_metrics:{user_id}"


def record_delivery(user_id: int, reminder_id: int, channel: str, success: bool, latency_ms: int = 0):
    """Record a reminder delivery attempt."""
    event = {
        "reminder_id": reminder_id,
        "channel": channel,
        "success": success,
        "latency_ms": latency_ms,
        "timestamp": datetime.utcnow().isoformat(),
    }
    key = METRICS_KEY.format(user_id=user_id)
    redis_client.lpush(key, json.dumps(event))
    redis_client.ltrim(key, 0, 499)  # Keep last 500
    redis_client.expire(key, 86400 * 90)  # 90 days


def get_delivery_metrics(user_id: int, days: int = 30) -> dict:
    """Get reminder delivery metrics for a user."""
    key = METRICS_KEY.format(user_id=user_id)
    raw = redis_client.lrange(key, 0, -1)
    events = [json.loads(r) for r in raw]

    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    events = [e for e in events if e["timestamp"] >= cutoff]

    if not events:
        return {
            "total_sent": 0,
            "success_rate": 0,
            "avg_latency_ms": 0,
            "by_channel": {},
        }

    total = len(events)
    successes = sum(1 for e in events if e["success"])
    avg_latency = sum(e["latency_ms"] for e in events) / total if total else 0

    # By channel breakdown
    by_channel = {}
    for e in events:
        ch = e["channel"]
        by_channel.setdefault(ch, {"total": 0, "success": 0, "latency_sum": 0})
        by_channel[ch]["total"] += 1
        if e["success"]:
            by_channel[ch]["success"] += 1
        by_channel[ch]["latency_sum"] += e["latency_ms"]

    channel_metrics = {}
    for ch, data in by_channel.items():
        channel_metrics[ch] = {
            "total": data["total"],
            "success_rate": round(data["success"] / data["total"] * 100, 1) if data["total"] else 0,
            "avg_latency_ms": round(data["latency_sum"] / data["total"]) if data["total"] else 0,
        }

    return {
        "period_days": days,
        "total_sent": total,
        "success_rate": round(successes / total * 100, 1),
        "failure_count": total - successes,
        "avg_latency_ms": round(avg_latency),
        "by_channel": channel_metrics,
    }
