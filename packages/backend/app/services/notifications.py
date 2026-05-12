"""Notification priority and grouping system."""

from datetime import datetime
from enum import Enum

from ..extensions import db, redis_client
import json
import logging

logger = logging.getLogger("finmind.notifications")


class Priority(str, Enum):
    CRITICAL = "critical"  # Payment failures, security alerts
    HIGH = "high"          # Bills due today, overspend warnings
    MEDIUM = "medium"      # Weekly digest, goal progress
    LOW = "low"            # Tips, suggestions


class NotificationGroup(str, Enum):
    SECURITY = "security"
    BILLING = "billing"
    INSIGHTS = "insights"
    GOALS = "goals"
    SYSTEM = "system"


NOTIFICATION_KEY = "notifications:{user_id}"


def send_notification(
    user_id: int,
    title: str,
    message: str,
    priority: Priority = Priority.MEDIUM,
    group: NotificationGroup = NotificationGroup.SYSTEM,
    data: dict | None = None,
):
    """Queue a notification for a user with priority and grouping."""
    notification = {
        "id": f"{user_id}:{datetime.utcnow().timestamp()}",
        "title": title,
        "message": message,
        "priority": priority.value,
        "group": group.value,
        "data": data or {},
        "read": False,
        "created_at": datetime.utcnow().isoformat(),
    }

    key = NOTIFICATION_KEY.format(user_id=user_id)
    redis_client.lpush(key, json.dumps(notification))
    redis_client.ltrim(key, 0, 99)  # Keep last 100
    redis_client.expire(key, 86400 * 30)  # 30 days

    logger.info("Notification sent: user=%d priority=%s group=%s", user_id, priority.value, group.value)


def get_notifications(user_id: int, group: str | None = None) -> list[dict]:
    """Get notifications for a user, optionally filtered by group.

    Returns notifications sorted by priority (critical first), then by time.
    """
    key = NOTIFICATION_KEY.format(user_id=user_id)
    raw = redis_client.lrange(key, 0, -1)
    notifications = [json.loads(r) for r in raw]

    if group:
        notifications = [n for n in notifications if n["group"] == group]

    # Sort: critical > high > medium > low, then newest first
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    notifications.sort(key=lambda n: (priority_order.get(n["priority"], 9), n["created_at"]))

    return notifications


def get_grouped_notifications(user_id: int) -> dict[str, list[dict]]:
    """Get notifications grouped by category."""
    all_notifs = get_notifications(user_id)
    grouped: dict[str, list[dict]] = {}
    for n in all_notifs:
        grouped.setdefault(n["group"], []).append(n)
    return grouped


def mark_read(user_id: int, notification_id: str) -> bool:
    """Mark a notification as read."""
    key = NOTIFICATION_KEY.format(user_id=user_id)
    raw = redis_client.lrange(key, 0, -1)

    for i, r in enumerate(raw):
        n = json.loads(r)
        if n["id"] == notification_id:
            n["read"] = True
            redis_client.lset(key, i, json.dumps(n))
            return True
    return False


def clear_notifications(user_id: int, group: str | None = None):
    """Clear notifications for a user."""
    key = NOTIFICATION_KEY.format(user_id=user_id)
    if group:
        raw = redis_client.lrange(key, 0, -1)
        kept = [r for r in raw if json.loads(r)["group"] != group]
        redis_client.delete(key)
        for r in reversed(kept):
            redis_client.lpush(key, r)
    else:
        redis_client.delete(key)
