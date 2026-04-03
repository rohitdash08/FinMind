"""Reminder reliability tracking and delivery metrics (issue #123)."""
from datetime import datetime, timedelta
from typing import Optional
from ..extensions import db
from ..models import Reminder, ReminderDeliveryLog, ReminderDeliveryStatus


def log_delivery_attempt(
    reminder_id: int,
    user_id: int,
    channel: str,
    status: ReminderDeliveryStatus,
    error_message: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> ReminderDeliveryLog:
    """Record a delivery attempt for a reminder."""
    now = datetime.utcnow()
    log = ReminderDeliveryLog(
        reminder_id=reminder_id,
        user_id=user_id,
        channel=channel,
        status=status,
        attempted_at=now,
        delivered_at=now if status == ReminderDeliveryStatus.SENT else None,
        error_message=error_message,
        latency_ms=latency_ms,
    )
    db.session.add(log)
    db.session.commit()
    return log


def get_reliability_metrics(user_id: int, days: int = 30) -> dict:
    """
    Compute delivery reliability metrics for a user's reminders over the last *days* days.

    Returns:
      - total_attempts   (int)
      - sent             (int)
      - failed           (int)
      - bounced          (int)
      - pending          (int)
      - delivery_rate    (float, 0-1)
      - failure_rate     (float, 0-1)
      - avg_latency_ms   (float | None)
      - channel_breakdown (list of {channel, sent, failed, delivery_rate})
      - recent_failures  (list of {reminder_id, channel, error, attempted_at})
    """
    since = datetime.utcnow() - timedelta(days=days)
    logs = (
        db.session.query(ReminderDeliveryLog)
        .filter(
            ReminderDeliveryLog.user_id == user_id,
            ReminderDeliveryLog.attempted_at >= since,
        )
        .all()
    )

    total = len(logs)
    sent = sum(1 for l in logs if l.status == ReminderDeliveryStatus.SENT)
    failed = sum(1 for l in logs if l.status == ReminderDeliveryStatus.FAILED)
    bounced = sum(1 for l in logs if l.status == ReminderDeliveryStatus.BOUNCED)
    pending = sum(1 for l in logs if l.status == ReminderDeliveryStatus.PENDING)

    delivery_rate = round(sent / total, 4) if total else 0.0
    failure_rate = round((failed + bounced) / total, 4) if total else 0.0

    latencies = [l.latency_ms for l in logs if l.latency_ms is not None]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None

    # Channel breakdown
    channels: dict[str, dict] = {}
    for l in logs:
        ch = l.channel
        if ch not in channels:
            channels[ch] = {"sent": 0, "failed": 0, "total": 0}
        channels[ch]["total"] += 1
        if l.status == ReminderDeliveryStatus.SENT:
            channels[ch]["sent"] += 1
        elif l.status in (ReminderDeliveryStatus.FAILED, ReminderDeliveryStatus.BOUNCED):
            channels[ch]["failed"] += 1

    channel_breakdown = [
        {
            "channel": ch,
            "sent": v["sent"],
            "failed": v["failed"],
            "delivery_rate": round(v["sent"] / v["total"], 4) if v["total"] else 0.0,
        }
        for ch, v in sorted(channels.items())
    ]

    # Recent failures
    recent_failures = [
        {
            "reminder_id": l.reminder_id,
            "channel": l.channel,
            "error": l.error_message,
            "attempted_at": l.attempted_at.isoformat(),
        }
        for l in sorted(logs, key=lambda x: x.attempted_at, reverse=True)
        if l.status in (ReminderDeliveryStatus.FAILED, ReminderDeliveryStatus.BOUNCED)
    ][:10]

    return {
        "period_days": days,
        "total_attempts": total,
        "sent": sent,
        "failed": failed,
        "bounced": bounced,
        "pending": pending,
        "delivery_rate": delivery_rate,
        "failure_rate": failure_rate,
        "avg_latency_ms": avg_latency,
        "channel_breakdown": channel_breakdown,
        "recent_failures": recent_failures,
    }
