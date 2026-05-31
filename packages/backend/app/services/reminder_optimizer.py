from datetime import datetime
from ..extensions import db
from ..models import EngagementEvent, ReminderABTest, Reminder
import logging
import random

logger = logging.getLogger("finmind.reminder_optimizer")

AB_TEST_VARIANTS = ["morning", "afternoon", "evening"]
MORNING_HOUR = 9
AFTERNOON_HOUR = 14
EVENING_HOUR = 19


def record_engagement(uid: int, event_type: str, channel: str):
    event = EngagementEvent(user_id=uid, event_type=event_type, channel=channel)
    db.session.add(event)
    db.session.commit()


def get_optimization_insights(uid: int) -> dict:
    events = (
        db.session.query(EngagementEvent)
        .filter_by(user_id=uid)
        .order_by(EngagementEvent.timestamp)
        .all()
    )
    if not events:
        return {
            "recommended_hour": MORNING_HOUR,
            "engagement_by_hour": {},
            "best_channel": "email",
            "sample_size": 0,
        }

    hour_counts: dict[int, int] = {}
    channel_counts: dict[str, int] = {}
    for e in events:
        hour = e.timestamp.hour
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
        channel_counts[e.channel] = channel_counts.get(e.channel, 0) + 1

    best_hour = max(hour_counts, key=hour_counts.get)
    best_channel = max(channel_counts, key=channel_counts.get) if channel_counts else "email"

    return {
        "recommended_hour": best_hour,
        "engagement_by_hour": {str(h): c for h, c in sorted(hour_counts.items())},
        "best_channel": best_channel,
        "sample_size": len(events),
    }


def optimize_reminder_times(uid: int) -> int:
    insights = get_optimization_insights(uid)
    recommended_hour = insights["recommended_hour"]

    reminders = (
        db.session.query(Reminder)
        .filter_by(user_id=uid, sent=False)
        .all()
    )
    updated = 0
    for r in reminders:
        new_send = r.send_at.replace(hour=recommended_hour, minute=0, second=0)
        if new_send != r.send_at:
            r.send_at = new_send
            updated += 1
    db.session.commit()
    logger.info("Optimized reminders user=%s count=%s hour=%s", uid, updated, recommended_hour)
    return updated


def assign_ab_test_group(uid: int) -> str:
    variant = random.choice(AB_TEST_VARIANTS)
    test_group = f"time_variant_{variant}"
    record = ReminderABTest(
        user_id=uid,
        test_group=test_group,
        variant=variant,
        metric="open_rate",
        value=0.0,
    )
    db.session.add(record)
    db.session.commit()
    return variant


def get_ab_test_results(uid: int) -> dict:
    results = (
        db.session.query(ReminderABTest)
        .filter_by(user_id=uid)
        .all()
    )
    grouped: dict[str, list] = {}
    for r in results:
        grouped.setdefault(r.variant, []).append(r.value)
    return {
        variant: {
            "avg_metric": round(sum(vals) / len(vals), 2) if vals else 0,
            "count": len(vals),
        }
        for variant, vals in grouped.items()
    }
