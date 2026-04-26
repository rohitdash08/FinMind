"""
Smart reminder timing optimization service (#111).

Analyses past reminder send times and user payment behaviour to recommend
the optimal time-of-day and days-before-due for future reminders.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Bill, Reminder


def _sent_reminders_for_user(uid: int) -> list[Reminder]:
    """Return all sent reminders for a user."""
    return (
        db.session.query(Reminder)
        .filter_by(user_id=uid, sent=True)
        .all()
    )


def optimal_reminder_timing(uid: int) -> dict[str, Any]:
    """
    Recommend optimal reminder timing based on historical patterns.

    Heuristics:
    - Hour of day: pick the most common hour from past sent reminders,
      defaulting to 09:00 if no history.
    - Days before due: analyse how many days before a bill's due date
      each sent reminder was scheduled. Use the median, defaulting to 3.
    - Day of week: pick the weekday with the most sent reminders, avoiding
      weekends when possible.

    Returns a dict with recommendations and the confidence level
    (``low`` / ``medium`` / ``high``) based on how much history exists.
    """
    sent = _sent_reminders_for_user(uid)

    # Default recommendations
    recommended_hour = 9
    recommended_days_before = 3
    recommended_weekday = "Monday"  # 0 = Monday
    confidence = "low"

    if sent:
        # Hour-of-day analysis
        hours = [r.send_at.hour for r in sent]
        hour_counts = Counter(hours)
        recommended_hour = hour_counts.most_common(1)[0][0]

        # Weekday analysis — prefer weekdays
        weekdays = [r.send_at.weekday() for r in sent]
        weekday_counts = Counter(weekdays)
        # prefer Mon-Fri (0-4)
        best_weekday = min(
            range(5),
            key=lambda d: (-weekday_counts.get(d, 0), d),
        )
        recommended_weekday = [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
        ][best_weekday]

        # Days-before-due analysis: join reminders with their bills
        days_before_list = []
        for reminder in sent:
            if reminder.bill_id:
                bill = db.session.get(Bill, reminder.bill_id)
                if bill and bill.due_date:
                    # bill.due_date is a date; reminder.send_at is datetime
                    delta = (
                        datetime.combine(bill.due_date, datetime.min.time())
                        - reminder.send_at
                    ).days
                    if 0 <= delta <= 14:
                        days_before_list.append(delta)

        if days_before_list:
            sorted_days = sorted(days_before_list)
            recommended_days_before = sorted_days[len(sorted_days) // 2]

        confidence = "high" if len(sent) >= 10 else "medium" if len(sent) >= 3 else "low"

    return {
        "recommended_hour": recommended_hour,
        "recommended_send_time": f"{recommended_hour:02d}:00",
        "recommended_days_before_due": recommended_days_before,
        "recommended_weekday": recommended_weekday,
        "confidence": confidence,
        "sample_size": len(sent),
        "tip": (
            f"Based on your history, send reminders on {recommended_weekday} "
            f"at {recommended_hour:02d}:00, {recommended_days_before} day(s) "
            "before each bill is due."
        ),
    }


def suggest_reminder_send_at(
    uid: int, bill_due_date_iso: str
) -> dict[str, Any]:
    """
    Given a bill due date, suggest a concrete send_at datetime.

    Combines the optimal timing recommendation with the provided due date.
    """
    from datetime import date

    timing = optimal_reminder_timing(uid)
    due = date.fromisoformat(bill_due_date_iso)
    target_date = due - timedelta(days=timing["recommended_days_before_due"])
    send_at = datetime.combine(
        target_date,
        datetime.min.time().replace(hour=timing["recommended_hour"]),
    )
    return {
        **timing,
        "bill_due_date": bill_due_date_iso,
        "suggested_send_at": send_at.isoformat(),
    }
