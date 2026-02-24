"""
reminder_metrics.py — Reminder reliability tracking and delivery metrics.

Aggregates delivery log data to surface success rates, failure patterns,
channel performance, and latency statistics.

Public API:
    get_reminder_metrics(uid, session, days=30) -> dict
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Reminder, ReminderDeliveryLog

logger = logging.getLogger("finmind.reminder_metrics")


def get_reminder_metrics(
    uid: int,
    session: Session,
    days: int = 30,
) -> dict:
    """
    Return delivery reliability metrics for a user's reminders.

    Returns:
    {
      "period_days": <int>,
      "total_reminders_scheduled": <int>,
      "total_attempts": <int>,
      "total_sent": <int>,
      "total_failed": <int>,
      "success_rate": <float 0.0-1.0>,
      "by_channel": {
        "email":     {"attempts": <int>, "sent": <int>, "failed": <int>, "success_rate": <float>},
        "whatsapp":  { ... },
        ...
      },
      "avg_latency_seconds": <float|null>,
      "recent_failures": [
        {"reminder_id": <int>, "channel": <str>, "attempted_at": "<ISO>", "error_message": <str|null>},
        ...  (last 5)
      ],
      "pending_reminders": <int>,
    }
    """
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # Only look at delivery logs for this user's reminders
    user_reminder_ids = [
        r.id for r in session.query(Reminder.id).filter_by(user_id=uid).all()
    ]

    if not user_reminder_ids:
        # Still compute pending/scheduled counts even with no logs
        total_scheduled = session.query(func.count(Reminder.id)).filter(
            Reminder.user_id == uid,
        ).scalar() or 0
        pending = session.query(func.count(Reminder.id)).filter(
            Reminder.user_id == uid,
            Reminder.sent == False,  # noqa: E712
        ).scalar() or 0
        result = _empty_metrics(days)
        result["total_reminders_scheduled"] = total_scheduled
        result["pending_reminders"] = pending
        return result

    # Base query for delivery logs in period
    logs_q = session.query(ReminderDeliveryLog).filter(
        ReminderDeliveryLog.reminder_id.in_(user_reminder_ids),
        ReminderDeliveryLog.attempted_at >= since,
    )

    all_logs = logs_q.all()
    total_attempts = len(all_logs)
    total_sent = sum(1 for log in all_logs if log.success)
    total_failed = total_attempts - total_sent
    success_rate = round(total_sent / total_attempts, 4) if total_attempts else 0.0

    # Per-channel breakdown
    channels: dict[str, dict] = {}
    for log in all_logs:
        ch = log.channel or "unknown"
        if ch not in channels:
            channels[ch] = {"attempts": 0, "sent": 0, "failed": 0}
        channels[ch]["attempts"] += 1
        if log.success:
            channels[ch]["sent"] += 1
        else:
            channels[ch]["failed"] += 1
    for ch_data in channels.values():
        ch_data["success_rate"] = (
            round(ch_data["sent"] / ch_data["attempts"], 4)
            if ch_data["attempts"]
            else 0.0
        )

    # Average latency (only for successful sends with latency data)
    latencies = [
        log.latency_seconds
        for log in all_logs
        if log.success and log.latency_seconds is not None
    ]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None

    # Recent failures (last 5)
    failures = sorted(
        [log for log in all_logs if not log.success],
        key=lambda log: log.attempted_at,
        reverse=True,
    )[:5]
    recent_failures = [
        {
            "reminder_id": f.reminder_id,
            "channel": f.channel,
            "attempted_at": f.attempted_at.isoformat(),
            "error_message": f.error_message,
        }
        for f in failures
    ]

    # Pending (scheduled but not yet sent)
    pending = (
        session.query(func.count(Reminder.id))
        .filter(
            Reminder.user_id == uid,
            Reminder.sent == False,  # noqa: E712
        )
        .scalar()
        or 0
    )

    total_scheduled = (
        session.query(func.count(Reminder.id))
        .filter(
            Reminder.user_id == uid,
        )
        .scalar()
        or 0
    )

    logger.info(
        "Reminder metrics user=%s days=%d attempts=%d success_rate=%.2f",
        uid,
        days,
        total_attempts,
        success_rate,
    )

    return {
        "period_days": days,
        "total_reminders_scheduled": total_scheduled,
        "total_attempts": total_attempts,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "success_rate": success_rate,
        "by_channel": channels,
        "avg_latency_seconds": avg_latency,
        "recent_failures": recent_failures,
        "pending_reminders": pending,
    }


def _empty_metrics(days: int) -> dict:
    return {
        "period_days": days,
        "total_reminders_scheduled": 0,
        "total_attempts": 0,
        "total_sent": 0,
        "total_failed": 0,
        "success_rate": 0.0,
        "by_channel": {},
        "avg_latency_seconds": None,
        "recent_failures": [],
        "pending_reminders": 0,
    }
