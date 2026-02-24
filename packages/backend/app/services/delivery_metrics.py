"""Reminder reliability tracking & delivery metrics (#123).

Tracks reminder delivery success/failure rates and provides
metrics for monitoring reminder system health.
"""

import logging
from datetime import datetime, date, timedelta

from ..extensions import db

logger = logging.getLogger("finmind.delivery_metrics")


class DeliveryLog(db.Model):
    __tablename__ = "delivery_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reminder_id = db.Column(db.Integer, nullable=False)
    channel = db.Column(db.String(50), default="in_app", nullable=False)  # in_app, email, push
    status = db.Column(db.String(20), nullable=False)  # SENT, DELIVERED, FAILED, SKIPPED
    error_message = db.Column(db.String(500))
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    delivered_at = db.Column(db.DateTime)
    latency_ms = db.Column(db.Integer)  # delivery latency in milliseconds


def log_delivery(user_id, reminder_id, channel="in_app", status="SENT", error=None, latency_ms=None):
    """Log a reminder delivery attempt."""
    entry = DeliveryLog(
        user_id=user_id,
        reminder_id=reminder_id,
        channel=channel,
        status=status,
        error_message=error[:500] if error else None,
        delivered_at=datetime.utcnow() if status == "DELIVERED" else None,
        latency_ms=latency_ms,
    )
    db.session.add(entry)
    db.session.commit()
    logger.info("Delivery log: reminder=%s channel=%s status=%s", reminder_id, channel, status)
    return entry


def get_delivery_metrics(user_id, days=30):
    """Get delivery reliability metrics for the past N days."""
    from sqlalchemy import func

    cutoff = datetime.utcnow() - timedelta(days=days)
    base = DeliveryLog.query.filter(
        DeliveryLog.user_id == user_id,
        DeliveryLog.sent_at >= cutoff,
    )

    total = base.count()
    if total == 0:
        return {
            "period_days": days,
            "total_deliveries": 0,
            "success_rate": 0.0,
            "by_status": {},
            "by_channel": {},
            "avg_latency_ms": None,
        }

    # By status
    status_counts = (
        base.with_entities(DeliveryLog.status, func.count(DeliveryLog.id))
        .group_by(DeliveryLog.status)
        .all()
    )
    by_status = {s: c for s, c in status_counts}

    # By channel
    channel_counts = (
        base.with_entities(DeliveryLog.channel, func.count(DeliveryLog.id))
        .group_by(DeliveryLog.channel)
        .all()
    )
    by_channel = {ch: c for ch, c in channel_counts}

    # Success rate
    delivered = by_status.get("DELIVERED", 0) + by_status.get("SENT", 0)
    success_rate = round(delivered / total * 100, 1)

    # Average latency
    avg_lat = (
        base.with_entities(func.avg(DeliveryLog.latency_ms))
        .filter(DeliveryLog.latency_ms.isnot(None))
        .scalar()
    )

    return {
        "period_days": days,
        "total_deliveries": total,
        "success_rate": success_rate,
        "by_status": by_status,
        "by_channel": by_channel,
        "avg_latency_ms": round(float(avg_lat)) if avg_lat else None,
    }


def get_delivery_history(user_id, reminder_id=None, limit=50):
    """Get delivery history, optionally filtered by reminder."""
    q = DeliveryLog.query.filter_by(user_id=user_id)
    if reminder_id:
        q = q.filter_by(reminder_id=reminder_id)
    return q.order_by(DeliveryLog.sent_at.desc()).limit(limit).all()
