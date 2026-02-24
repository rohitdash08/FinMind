"""Notification priority & grouping system (#122).

Provides a notification model with priority levels and grouping,
so users see organized, prioritized alerts.
"""

import logging
from datetime import datetime
from enum import Enum

from ..extensions import db

logger = logging.getLogger("finmind.notifications")


class NotificationPriority(str, Enum):
    CRITICAL = "CRITICAL"   # e.g. bill overdue, account breach
    HIGH = "HIGH"           # e.g. budget exceeded, large transaction
    MEDIUM = "MEDIUM"       # e.g. bill due soon, budget warning
    LOW = "LOW"             # e.g. weekly summary, tips


class NotificationGroup(str, Enum):
    BILLS = "BILLS"
    BUDGETS = "BUDGETS"
    TRANSACTIONS = "TRANSACTIONS"
    INSIGHTS = "INSIGHTS"
    SYSTEM = "SYSTEM"


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    priority = db.Column(db.String(20), default=NotificationPriority.MEDIUM.value, nullable=False)
    group = db.Column(db.String(20), default=NotificationGroup.SYSTEM.value, nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def create_notification(user_id, title, message, priority=NotificationPriority.MEDIUM, group=NotificationGroup.SYSTEM):
    """Create a new notification."""
    n = Notification(
        user_id=user_id,
        title=title,
        message=message,
        priority=priority.value if isinstance(priority, NotificationPriority) else priority,
        group=group.value if isinstance(group, NotificationGroup) else group,
    )
    db.session.add(n)
    db.session.commit()
    logger.info("Notification created id=%s user=%s priority=%s group=%s", n.id, user_id, n.priority, n.group)
    return n


def get_notifications(user_id, unread_only=False, group=None, limit=50):
    """Get notifications sorted by priority then recency."""
    priority_order = {
        NotificationPriority.CRITICAL.value: 0,
        NotificationPriority.HIGH.value: 1,
        NotificationPriority.MEDIUM.value: 2,
        NotificationPriority.LOW.value: 3,
    }
    q = Notification.query.filter_by(user_id=user_id)
    if unread_only:
        q = q.filter_by(read=False)
    if group:
        q = q.filter_by(group=group.upper())
    items = q.order_by(Notification.created_at.desc()).limit(limit).all()
    # Sort by priority in Python (DB-agnostic)
    items.sort(key=lambda n: (priority_order.get(n.priority, 99), -n.id))
    return items


def get_grouped_notifications(user_id, unread_only=False):
    """Get notifications grouped by their group field."""
    items = get_notifications(user_id, unread_only=unread_only, limit=200)
    groups = {}
    for n in items:
        groups.setdefault(n.group, []).append(n)
    return groups


def mark_read(user_id, notification_ids):
    """Mark notifications as read."""
    count = Notification.query.filter(
        Notification.user_id == user_id,
        Notification.id.in_(notification_ids),
    ).update({"read": True}, synchronize_session=False)
    db.session.commit()
    return count


def mark_all_read(user_id):
    """Mark all notifications as read."""
    count = Notification.query.filter_by(user_id=user_id, read=False).update(
        {"read": True}, synchronize_session=False
    )
    db.session.commit()
    return count
