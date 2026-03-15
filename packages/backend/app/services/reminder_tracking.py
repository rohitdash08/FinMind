"""Reminder reliability tracking and delivery metrics.

Provides:
- Delivery event recording (sent, delivered, failed, bounced)
- Multi-channel tracking (email, push, SMS, in-app)
- Retry management with attempt counting
- Open/click engagement tracking
- Reliability metrics and statistics
- Channel performance analysis
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db
from app.models import ReminderDelivery, Reminder


# ─── Delivery Recording ─────────────────────────────────────────────


def record_delivery_attempt(reminder_id: int, user_id: int,
                            channel: str = "email",
                            status: str = "pending") -> dict:
    """Record a new delivery attempt.

    Args:
        reminder_id: Reminder ID
        user_id: User ID
        channel: Delivery channel (email, push, sms, in_app)
        status: Initial status

    Returns:
        Dict with delivery record info
    """
    # Count previous attempts
    prev_attempts = ReminderDelivery.query.filter_by(
        reminder_id=reminder_id, channel=channel
    ).count()

    delivery = ReminderDelivery(
        reminder_id=reminder_id,
        user_id=user_id,
        channel=channel,
        status=status,
        attempt_number=prev_attempts + 1,
    )
    db.session.add(delivery)
    db.session.commit()

    return _delivery_to_dict(delivery)


def mark_sent(delivery_id: int, response_code: str = "200") -> dict | None:
    """Mark a delivery as sent.

    Args:
        delivery_id: Delivery record ID
        response_code: Server response code

    Returns:
        Updated delivery dict or None
    """
    delivery = db.session.get(ReminderDelivery, delivery_id)
    if not delivery:
        return None

    delivery.status = "sent"
    delivery.sent_at = datetime.utcnow()
    delivery.response_code = response_code
    db.session.commit()

    return _delivery_to_dict(delivery)


def mark_delivered(delivery_id: int, latency_ms: int = 0) -> dict | None:
    """Mark a delivery as delivered.

    Args:
        delivery_id: Delivery record ID
        latency_ms: Delivery latency in milliseconds

    Returns:
        Updated delivery dict or None
    """
    delivery = db.session.get(ReminderDelivery, delivery_id)
    if not delivery:
        return None

    delivery.status = "delivered"
    delivery.delivered_at = datetime.utcnow()
    delivery.latency_ms = latency_ms
    if not delivery.sent_at:
        delivery.sent_at = datetime.utcnow()
    db.session.commit()

    return _delivery_to_dict(delivery)


def mark_failed(delivery_id: int, reason: str = "",
                response_code: str = "") -> dict | None:
    """Mark a delivery as failed.

    Args:
        delivery_id: Delivery record ID
        reason: Failure reason
        response_code: Server response code

    Returns:
        Updated delivery dict or None
    """
    delivery = db.session.get(ReminderDelivery, delivery_id)
    if not delivery:
        return None

    delivery.status = "failed"
    delivery.failed_at = datetime.utcnow()
    delivery.failure_reason = reason[:256] if reason else None
    delivery.response_code = response_code or None
    db.session.commit()

    return _delivery_to_dict(delivery)


def mark_bounced(delivery_id: int, reason: str = "") -> dict | None:
    """Mark a delivery as bounced.

    Args:
        delivery_id: Delivery record ID
        reason: Bounce reason

    Returns:
        Updated delivery dict or None
    """
    delivery = db.session.get(ReminderDelivery, delivery_id)
    if not delivery:
        return None

    delivery.status = "bounced"
    delivery.failed_at = datetime.utcnow()
    delivery.failure_reason = reason[:256] if reason else None
    db.session.commit()

    return _delivery_to_dict(delivery)


def record_opened(delivery_id: int) -> dict | None:
    """Record that a delivered message was opened.

    Args:
        delivery_id: Delivery record ID

    Returns:
        Updated delivery dict or None
    """
    delivery = db.session.get(ReminderDelivery, delivery_id)
    if not delivery:
        return None

    delivery.opened = True
    delivery.opened_at = datetime.utcnow()
    db.session.commit()

    return _delivery_to_dict(delivery)


def record_clicked(delivery_id: int) -> dict | None:
    """Record that a delivered message link was clicked.

    Args:
        delivery_id: Delivery record ID

    Returns:
        Updated delivery dict or None
    """
    delivery = db.session.get(ReminderDelivery, delivery_id)
    if not delivery:
        return None

    delivery.clicked = True
    delivery.clicked_at = datetime.utcnow()
    if not delivery.opened:
        delivery.opened = True
        delivery.opened_at = datetime.utcnow()
    db.session.commit()

    return _delivery_to_dict(delivery)


# ─── Query Functions ─────────────────────────────────────────────────


def get_delivery_history(user_id: int, limit: int = 50,
                         channel: str | None = None,
                         status: str | None = None) -> list[dict]:
    """Get delivery history for a user.

    Args:
        user_id: User ID
        limit: Max records
        channel: Filter by channel
        status: Filter by status

    Returns:
        List of delivery dicts
    """
    query = ReminderDelivery.query.filter_by(user_id=user_id)

    if channel:
        query = query.filter_by(channel=channel)
    if status:
        query = query.filter_by(status=status)

    deliveries = (query.order_by(ReminderDelivery.created_at.desc())
                  .limit(limit).all())

    return [_delivery_to_dict(d) for d in deliveries]


def get_reminder_deliveries(reminder_id: int) -> list[dict]:
    """Get all delivery attempts for a specific reminder.

    Args:
        reminder_id: Reminder ID

    Returns:
        List of delivery dicts
    """
    deliveries = (ReminderDelivery.query
                  .filter_by(reminder_id=reminder_id)
                  .order_by(ReminderDelivery.attempt_number)
                  .all())

    return [_delivery_to_dict(d) for d in deliveries]


def get_reliability_metrics(user_id: int, days: int = 30) -> dict:
    """Calculate reliability metrics for a user.

    Args:
        user_id: User ID
        days: Lookback period

    Returns:
        Dict with reliability metrics
    """
    since = datetime.utcnow() - timedelta(days=days)
    deliveries = ReminderDelivery.query.filter(
        ReminderDelivery.user_id == user_id,
        ReminderDelivery.created_at >= since,
    ).all()

    total = len(deliveries)
    if total == 0:
        return {
            "period_days": days,
            "total_attempts": 0,
            "delivery_rate": 0.0,
            "failure_rate": 0.0,
            "bounce_rate": 0.0,
            "open_rate": 0.0,
            "click_rate": 0.0,
            "avg_latency_ms": 0,
            "by_channel": {},
            "by_status": {},
        }

    delivered = sum(1 for d in deliveries if d.status == "delivered")
    failed = sum(1 for d in deliveries if d.status == "failed")
    bounced = sum(1 for d in deliveries if d.status == "bounced")
    opened = sum(1 for d in deliveries if d.opened)
    clicked = sum(1 for d in deliveries if d.clicked)

    latencies = [d.latency_ms for d in deliveries if d.latency_ms]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

    # By channel
    by_channel = {}
    for d in deliveries:
        ch = d.channel or "unknown"
        if ch not in by_channel:
            by_channel[ch] = {"total": 0, "delivered": 0, "failed": 0}
        by_channel[ch]["total"] += 1
        if d.status == "delivered":
            by_channel[ch]["delivered"] += 1
        elif d.status in ("failed", "bounced"):
            by_channel[ch]["failed"] += 1

    # By status
    by_status = {}
    for d in deliveries:
        by_status[d.status] = by_status.get(d.status, 0) + 1

    return {
        "period_days": days,
        "total_attempts": total,
        "delivery_rate": round(delivered / total, 3) if total else 0.0,
        "failure_rate": round((failed + bounced) / total, 3) if total else 0.0,
        "bounce_rate": round(bounced / total, 3) if total else 0.0,
        "open_rate": round(opened / delivered, 3) if delivered else 0.0,
        "click_rate": round(clicked / delivered, 3) if delivered else 0.0,
        "avg_latency_ms": avg_latency,
        "by_channel": by_channel,
        "by_status": by_status,
    }


def get_channel_performance(user_id: int, days: int = 30) -> list[dict]:
    """Get performance breakdown by delivery channel.

    Args:
        user_id: User ID
        days: Lookback period

    Returns:
        List of channel performance dicts
    """
    since = datetime.utcnow() - timedelta(days=days)
    deliveries = ReminderDelivery.query.filter(
        ReminderDelivery.user_id == user_id,
        ReminderDelivery.created_at >= since,
    ).all()

    channels = {}
    for d in deliveries:
        ch = d.channel or "unknown"
        if ch not in channels:
            channels[ch] = {
                "channel": ch,
                "total": 0,
                "delivered": 0,
                "failed": 0,
                "bounced": 0,
                "opened": 0,
                "clicked": 0,
                "latencies": [],
            }
        channels[ch]["total"] += 1
        if d.status == "delivered":
            channels[ch]["delivered"] += 1
        elif d.status == "failed":
            channels[ch]["failed"] += 1
        elif d.status == "bounced":
            channels[ch]["bounced"] += 1
        if d.opened:
            channels[ch]["opened"] += 1
        if d.clicked:
            channels[ch]["clicked"] += 1
        if d.latency_ms:
            channels[ch]["latencies"].append(d.latency_ms)

    result = []
    for ch_data in channels.values():
        lats = ch_data.pop("latencies")
        ch_data["avg_latency_ms"] = int(sum(lats) / len(lats)) if lats else 0
        total = ch_data["total"]
        ch_data["delivery_rate"] = round(ch_data["delivered"] / total, 3) if total else 0.0
        ch_data["open_rate"] = round(
            ch_data["opened"] / ch_data["delivered"], 3
        ) if ch_data["delivered"] else 0.0
        result.append(ch_data)

    return sorted(result, key=lambda x: x["total"], reverse=True)


# ─── Helpers ─────────────────────────────────────────────────────────


def _delivery_to_dict(d: ReminderDelivery) -> dict:
    """Convert ReminderDelivery model to dict."""
    return {
        "id": d.id,
        "reminder_id": d.reminder_id,
        "user_id": d.user_id,
        "channel": d.channel,
        "status": d.status,
        "attempt_number": d.attempt_number,
        "sent_at": d.sent_at.isoformat() if d.sent_at else None,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        "failed_at": d.failed_at.isoformat() if d.failed_at else None,
        "failure_reason": d.failure_reason,
        "response_code": d.response_code,
        "latency_ms": d.latency_ms,
        "opened": d.opened,
        "opened_at": d.opened_at.isoformat() if d.opened_at else None,
        "clicked": d.clicked,
        "clicked_at": d.clicked_at.isoformat() if d.clicked_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
