import logging
from datetime import datetime

from sqlalchemy import func

from ..extensions import db
from ..models import (
    Reminder,
    ReminderDelivery,
    ReminderDeliveryStatus,
)
from ..services.reminders import send_reminder as _send_reminder

logger = logging.getLogger("finmind.reminder_tracking")

MAX_RETRY_ATTEMPTS = 3


def create_delivery(reminder: Reminder) -> ReminderDelivery:
    delivery = ReminderDelivery(
        reminder_id=reminder.id,
        user_id=reminder.user_id,
        channel=reminder.channel,
        status=ReminderDeliveryStatus.PENDING,
        attempt_count=0,
    )
    db.session.add(delivery)
    db.session.commit()
    return delivery


def send_with_tracking(reminder: Reminder) -> ReminderDelivery:
    delivery = (
        db.session.query(ReminderDelivery)
        .filter(ReminderDelivery.reminder_id == reminder.id)
        .first()
    )
    if not delivery:
        delivery = create_delivery(reminder)

    success = _send_reminder(reminder)
    delivery.attempt_count = (delivery.attempt_count or 0) + 1
    delivery.last_attempt_at = datetime.utcnow()

    if success:
        delivery.status = ReminderDeliveryStatus.SENT
        delivery.delivered_at = datetime.utcnow()
    else:
        if delivery.attempt_count >= MAX_RETRY_ATTEMPTS:
            delivery.status = ReminderDeliveryStatus.FAILED
            delivery.error_message = f"Failed after {MAX_RETRY_ATTEMPTS} attempts"
        else:
            delivery.status = ReminderDeliveryStatus.PENDING

    db.session.commit()
    return delivery


def record_click(reminder_id: int, user_id: int) -> bool:
    delivery = (
        db.session.query(ReminderDelivery)
        .filter(
            ReminderDelivery.reminder_id == reminder_id,
            ReminderDelivery.user_id == user_id,
        )
        .first()
    )
    if not delivery:
        return False
    delivery.status = ReminderDeliveryStatus.CLICKED
    delivery.clicked_at = datetime.utcnow()
    db.session.commit()
    return True


def get_delivery_metrics(user_id: int) -> dict:
    total = (
        db.session.query(func.count(ReminderDelivery.id))
        .filter(ReminderDelivery.user_id == user_id)
        .scalar()
    ) or 0

    by_status = {}
    for status in ReminderDeliveryStatus:
        count = (
            db.session.query(func.count(ReminderDelivery.id))
            .filter(
                ReminderDelivery.user_id == user_id,
                ReminderDelivery.status == status,
            )
            .scalar()
        ) or 0
        by_status[status.value] = count

    by_channel = {}
    channels = (
        db.session.query(
            ReminderDelivery.channel,
            func.count(ReminderDelivery.id),
        )
        .filter(ReminderDelivery.user_id == user_id)
        .group_by(ReminderDelivery.channel)
        .all()
    )
    for ch, cnt in channels:
        by_channel[ch] = cnt

    pending_retries = (
        db.session.query(func.count(ReminderDelivery.id))
        .filter(
            ReminderDelivery.user_id == user_id,
            ReminderDelivery.status == ReminderDeliveryStatus.PENDING,
            ReminderDelivery.attempt_count < MAX_RETRY_ATTEMPTS,
        )
        .scalar()
    ) or 0

    return {
        "total": total,
        "by_status": by_status,
        "by_channel": by_channel,
        "pending_retries": pending_retries,
        "max_retry_attempts": MAX_RETRY_ATTEMPTS,
    }


def retry_failed_deliveries(user_id: int, limit: int = 10) -> int:
    failed = (
        db.session.query(ReminderDelivery)
        .filter(
            ReminderDelivery.user_id == user_id,
            ReminderDelivery.status == ReminderDeliveryStatus.PENDING,
            ReminderDelivery.attempt_count < MAX_RETRY_ATTEMPTS,
        )
        .order_by(ReminderDelivery.last_attempt_at.asc().nullsfirst())
        .limit(limit)
        .all()
    )
    retried = 0
    for delivery in failed:
        reminder = db.session.get(Reminder, delivery.reminder_id)
        if not reminder:
            continue
        send_with_tracking(reminder)
        retried += 1
    return retried


def list_deliveries(user_id: int, limit: int = 50) -> list[dict]:
    items = (
        db.session.query(ReminderDelivery)
        .filter(ReminderDelivery.user_id == user_id)
        .order_by(ReminderDelivery.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": d.id,
            "reminder_id": d.reminder_id,
            "channel": d.channel,
            "status": d.status.value if d.status else "PENDING",
            "attempt_count": d.attempt_count,
            "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
            "clicked_at": d.clicked_at.isoformat() if d.clicked_at else None,
            "error_message": d.error_message,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in items
    ]
