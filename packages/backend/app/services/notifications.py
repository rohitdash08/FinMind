"""
Notification priority & grouping system (issue #122).
Priority levels: CRITICAL > HIGH > MEDIUM > LOW
Grouping: batch similar notifications, deduplicate within windows.
"""
import json, logging
from datetime import datetime, timezone
from enum import IntEnum
from ..extensions import redis_client

logger = logging.getLogger("finmind.notifications")

QUEUE_PREFIX = "notif:queue:"
GROUP_PREFIX = "notif:group:"
TTL = 60 * 60 * 24 * 7


class Priority(IntEnum):
    LOW = 0; MEDIUM = 1; HIGH = 2; CRITICAL = 3


PRIORITY_TTL = {Priority.CRITICAL: 60, Priority.HIGH: 300,
                Priority.MEDIUM: 3600, Priority.LOW: 86400}


def _utcnow(): return datetime.now(timezone.utc).isoformat()
def _qkey(user_id: int): return f"{QUEUE_PREFIX}{user_id}"
def _gkey(user_id: int, group: str): return f"{GROUP_PREFIX}{user_id}:{group}"


def push(user_id: int, title: str, body: str,
         priority: Priority = Priority.MEDIUM,
         group: str = None, dedup_key: str = None) -> bool:
    """
    Push a notification. Returns False if deduped.
    group: group name for batching (e.g. 'bills', 'budget_warning')
    dedup_key: suppress if identical key seen recently
    """
    if dedup_key:
        dk = f"notif:dedup:{user_id}:{dedup_key}"
        if redis_client.get(dk):
            logger.debug("Notification deduped: %s", dedup_key)
            return False
        redis_client.setex(dk, PRIORITY_TTL[priority], "1")

    notif = {"title": title, "body": body, "priority": int(priority),
             "priority_name": priority.name, "group": group,
             "created_at": _utcnow(), "read": False}

    # Push to sorted set with priority score
    score = int(priority) * 1e12 + datetime.now(timezone.utc).timestamp()
    redis_client.zadd(_qkey(user_id), {json.dumps(notif): score})
    redis_client.expire(_qkey(user_id), TTL)

    if group:
        redis_client.rpush(_gkey(user_id, group), json.dumps(notif))
        redis_client.expire(_gkey(user_id, group), TTL)

    logger.info("Notification pushed user=%d priority=%s title=%s", user_id, priority.name, title)
    return True


def get_notifications(user_id: int, limit: int = 20) -> list:
    """Return notifications sorted by priority (highest first)."""
    raw = redis_client.zrevrange(_qkey(user_id), 0, limit - 1)
    return [json.loads(r) for r in raw]


def get_group(user_id: int, group: str) -> list:
    """Return all notifications in a group."""
    raw = redis_client.lrange(_gkey(user_id, group), 0, -1)
    return [json.loads(r) for r in raw]


def clear_group(user_id: int, group: str):
    redis_client.delete(_gkey(user_id, group))


def unread_count(user_id: int) -> int:
    return redis_client.zcard(_qkey(user_id))
