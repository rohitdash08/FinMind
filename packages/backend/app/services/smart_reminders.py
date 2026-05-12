"""Smart reminder timing optimization.

Analyzes user behavior patterns to determine optimal reminder delivery times.
"""

from datetime import datetime, timedelta, time
from collections import Counter

from ..extensions import db
from ..models import Expense, Bill
import logging

logger = logging.getLogger("finmind.smart_reminders")


def get_optimal_reminder_time(user_id: int) -> dict:
    """Determine the best time to send reminders based on user activity patterns.

    Analyzes when the user typically logs expenses to find their most
    active hours, then suggests reminder times slightly before.
    """
    # Get last 60 days of expense creation times
    cutoff = datetime.utcnow() - timedelta(days=60)
    expenses = (
        db.session.query(Expense.created_at)
        .filter(Expense.user_id == user_id, Expense.created_at >= cutoff)
        .all()
    )

    if not expenses:
        return {
            "optimal_hour": 9,
            "optimal_minute": 0,
            "confidence": "low",
            "reason": "No activity data, using default morning time",
        }

    # Count activity by hour
    hour_counts = Counter(e.created_at.hour for e in expenses)
    peak_hour = hour_counts.most_common(1)[0][0]

    # Send reminder 1 hour before peak activity
    reminder_hour = (peak_hour - 1) % 24

    # Determine confidence
    total = len(expenses)
    peak_count = hour_counts[peak_hour]
    confidence = "high" if peak_count / total > 0.3 else "medium" if peak_count / total > 0.15 else "low"

    return {
        "optimal_hour": reminder_hour,
        "optimal_minute": 0,
        "confidence": confidence,
        "peak_activity_hour": peak_hour,
        "reason": f"User most active at {peak_hour}:00, reminder set for {reminder_hour}:00",
        "activity_distribution": dict(hour_counts.most_common(5)),
    }


def get_optimal_bill_reminder_days(user_id: int) -> dict:
    """Determine how many days before due date to send bill reminders.

    Based on user's payment patterns - if they usually pay early,
    remind earlier. If they pay last minute, remind more frequently.
    """
    bills = (
        db.session.query(Bill)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    if not bills:
        return {"days_before": [3, 1], "reason": "Default: 3 days and 1 day before"}

    # For now, use simple heuristic based on bill count
    if len(bills) > 10:
        return {"days_before": [7, 3, 1], "reason": "Many bills: remind 7, 3, and 1 day before"}
    elif len(bills) > 5:
        return {"days_before": [5, 1], "reason": "Moderate bills: remind 5 and 1 day before"}
    else:
        return {"days_before": [3, 1], "reason": "Few bills: remind 3 and 1 day before"}
