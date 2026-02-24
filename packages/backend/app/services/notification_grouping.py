"""
notification_grouping.py — Notification priority and grouping service.

Provides:
  - auto_priority(reminder, session) -> str   Priority inference from context
  - get_grouped_notifications(uid, session, include_sent=False) -> dict
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Bill, NotificationPriority, NotificationType, Reminder

logger = logging.getLogger("finmind.notifications")

# Days-to-due thresholds for auto-priority
_URGENT_DAYS = 1
_HIGH_DAYS   = 3
_NORMAL_DAYS = 7


def auto_priority(reminder: Reminder, session: Session) -> str:
    """
    Infer notification priority from context.

    Rules (in priority order):
    1. BILL_REMINDER with bill due in <= 1 day  → URGENT
    2. BILL_REMINDER with bill due in <= 3 days → HIGH
    3. BILL_REMINDER with bill due in <= 7 days → NORMAL
    4. BILL_REMINDER due > 7 days away          → LOW
    5. CUSTOM / SYSTEM                          → NORMAL
    """
    if reminder.notification_type == NotificationType.BILL_REMINDER.value and reminder.bill_id:
        bill = session.get(Bill, reminder.bill_id)
        if bill:
            days_left = (bill.next_due_date - date.today()).days
            if days_left <= _URGENT_DAYS:
                return NotificationPriority.URGENT.value
            if days_left <= _HIGH_DAYS:
                return NotificationPriority.HIGH.value
            if days_left <= _NORMAL_DAYS:
                return NotificationPriority.NORMAL.value
            return NotificationPriority.LOW.value
    return NotificationPriority.NORMAL.value


def get_grouped_notifications(
    uid: int,
    session: Session,
    include_sent: bool = False,
) -> dict:
    """
    Return notifications grouped by priority, then by notification_type.

    Returns:
    {
      "total": <int>,
      "by_priority": {
        "URGENT": {"count": <int>, "items": [<notification>, ...]},
        "HIGH":   {"count": <int>, "items": [...]},
        "NORMAL": {"count": <int>, "items": [...]},
        "LOW":    {"count": <int>, "items": [...]},
      },
      "by_type": {
        "BILL_REMINDER": {"count": <int>, "items": [...]},
        "CUSTOM":        {"count": <int>, "items": [...]},
        "SYSTEM":        {"count": <int>, "items": [...]},
      },
      "summary": {
        "urgent_count": <int>,
        "overdue_count": <int>,   # send_at < now and not sent
        "upcoming_24h": <int>,    # due within next 24 hours
      }
    }
    """
    q = session.query(Reminder).filter(Reminder.user_id == uid)
    if not include_sent:
        q = q.filter(Reminder.sent == False)  # noqa: E712
    reminders = q.order_by(Reminder.send_at.asc()).all()

    now = datetime.utcnow()

    def serialise(r: Reminder) -> dict:
        return {
            "id":                r.id,
            "message":           r.message,
            "send_at":           r.send_at.isoformat(),
            "sent":              r.sent,
            "channel":           r.channel,
            "priority":          r.priority,
            "notification_type": r.notification_type,
            "bill_id":           r.bill_id,
            "overdue":           r.send_at < now and not r.sent,
        }

    by_priority: dict[str, dict] = {
        p.value: {"count": 0, "items": []}
        for p in NotificationPriority
    }
    by_type: dict[str, dict] = {
        t.value: {"count": 0, "items": []}
        for t in NotificationType
    }

    overdue_count = 0
    upcoming_24h  = 0
    cutoff_24h    = now + timedelta(hours=24)

    for r in reminders:
        item = serialise(r)
        prio  = r.priority          or NotificationPriority.NORMAL.value
        ntype = r.notification_type or NotificationType.CUSTOM.value

        if prio in by_priority:
            by_priority[prio]["count"] += 1
            by_priority[prio]["items"].append(item)
        if ntype in by_type:
            by_type[ntype]["count"] += 1
            by_type[ntype]["items"].append(item)

        if item["overdue"]:
            overdue_count += 1
        if not r.sent and now <= r.send_at <= cutoff_24h:
            upcoming_24h += 1

    logger.info(
        "Grouped notifications user=%s total=%d urgent=%d overdue=%d",
        uid, len(reminders), by_priority["URGENT"]["count"], overdue_count,
    )

    return {
        "total": len(reminders),
        "by_priority": by_priority,
        "by_type": by_type,
        "summary": {
            "urgent_count":  by_priority["URGENT"]["count"],
            "overdue_count": overdue_count,
            "upcoming_24h":  upcoming_24h,
        },
    }
