import logging
from datetime import datetime

from sqlalchemy import func

from ..extensions import db
from ..models import Notification, NotificationPriority, Reminder

logger = logging.getLogger("finmind.notification_priority")

PRIORITY_ORDER = {
    NotificationPriority.URGENT: 0,
    NotificationPriority.HIGH: 1,
    NotificationPriority.NORMAL: 2,
    NotificationPriority.LOW: 3,
}


def create_notification(
    user_id: int,
    title: str,
    body: str,
    notification_type: str = "general",
    priority: NotificationPriority = NotificationPriority.NORMAL,
    group_key: str | None = None,
) -> Notification:
    existing = None
    if group_key:
        existing = (
            db.session.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.group_key == group_key,
                Notification.read.is_(False),
            )
            .first()
        )
    if existing:
        existing.body = body
        existing.created_at = datetime.utcnow()
        existing.priority = max(
            [existing.priority, priority],
            key=lambda p: PRIORITY_ORDER.get(p, 99),
        )
        db.session.commit()
        return existing

    notification = Notification(
        user_id=user_id,
        title=title,
        body=body,
        notification_type=notification_type,
        priority=priority,
        group_key=group_key,
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def create_due_soon_notifications(user_id: int, reminders: list[Reminder]) -> list[Notification]:
    if not reminders:
        return []

    if len(reminders) == 1:
        n = create_notification(
            user_id=user_id, title="Bill Reminder", body=reminders[0].message,
            notification_type="bill_reminder", priority=NotificationPriority.HIGH,
            group_key=f"bill:{reminders[0].bill_id}" if reminders[0].bill_id else None,
        )
        return [n]

    total = len(reminders)
    body = f"You have {total} bills due soon:\n" + "\n".join(
        f"- {r.message}" for r in reminders[:5]
    )
    if total > 5:
        body += f"\n...and {total - 5} more"

    existing = (
        db.session.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.group_key == "batch:due_soon",
            Notification.read.is_(False),
        )
        .first()
    )
    if existing:
        existing.body = body
        existing.created_at = datetime.utcnow()
        db.session.commit()
        return [existing]

    notification = Notification(
        user_id=user_id,
        title=f"{total} Bills Due Soon",
        body=body,
        notification_type="batch_due_soon",
        priority=NotificationPriority.HIGH,
        group_key="batch:due_soon",
    )
    db.session.add(notification)
    db.session.commit()
    return [notification]


def list_notifications(
    user_id: int,
    unread_only: bool = False,
    priority: NotificationPriority | None = None,
    limit: int = 50,
) -> list[dict]:
    query = db.session.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.read.is_(False))
    if priority:
        query = query.filter(Notification.priority == priority)
    items = query.order_by(Notification.priority, Notification.created_at.desc()).limit(limit).all()

    return [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "notification_type": n.notification_type,
            "priority": n.priority.value if n.priority else "NORMAL",
            "group_key": n.group_key,
            "read": n.read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in items
    ]


def mark_read(notification_id: int, user_id: int) -> bool:
    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != user_id:
        return False
    notification.read = True
    db.session.commit()
    return True


def mark_all_read(user_id: int) -> int:
    count = (
        db.session.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read.is_(False))
        .update({"read": True})
    )
    db.session.commit()
    return count


def get_unread_count(user_id: int) -> dict:
    total = (
        db.session.query(func.count(Notification.id))
        .filter(Notification.user_id == user_id, Notification.read.is_(False))
        .scalar()
    ) or 0

    by_priority = {}
    for p in NotificationPriority:
        count = (
            db.session.query(func.count(Notification.id))
            .filter(
                Notification.user_id == user_id,
                Notification.read.is_(False),
                Notification.priority == p,
            )
            .scalar()
        ) or 0
        by_priority[p.value] = count

    return {"total": total, "by_priority": by_priority}
