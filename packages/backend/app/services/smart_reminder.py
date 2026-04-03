"""Smart reminder timing optimization.

Analyzes user behavior patterns to suggest optimal reminder times:
- When does the user typically pay bills?
- What day of week are they most active?
- How far ahead do they need reminders?

Uses historical expense/bill payment data to learn patterns.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timedelta
from typing import TypedDict

from sqlalchemy import func

from ..extensions import db
from ..models import Bill, Expense, Reminder

logger = logging.getLogger("finmind.smart_reminder")


class TimingRecommendation(TypedDict):
    optimal_day_of_week: int  # 0=Mon, 6=Sun
    optimal_day_name: str
    optimal_days_before_due: int
    activity_by_day: dict[str, int]
    avg_payment_lead_days: float
    confidence: str  # low | medium | high


def analyze_timing(user_id: int, lookback_days: int = 180) -> TimingRecommendation:
    """Analyze user behavior to recommend optimal reminder timing."""
    cutoff = date.today() - timedelta(days=lookback_days)

    # Analyze which days of week user creates expenses (proxy for activity)
    day_counts = _get_activity_by_day(user_id, cutoff)

    # Analyze payment lead time (how early before due date they pay)
    lead_days = _get_payment_lead_days(user_id, cutoff)

    # Find most active day
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    activity = {day_names[i]: day_counts.get(i, 0) for i in range(7)}

    if any(day_counts.values()):
        optimal_dow = max(day_counts, key=day_counts.get)
    else:
        optimal_dow = 0  # default Monday

    avg_lead = sum(lead_days) / len(lead_days) if lead_days else 3.0
    optimal_lead = max(1, min(14, round(avg_lead)))

    total_activity = sum(day_counts.values())
    if total_activity >= 50:
        confidence = "high"
    elif total_activity >= 20:
        confidence = "medium"
    else:
        confidence = "low"

    return TimingRecommendation(
        optimal_day_of_week=optimal_dow,
        optimal_day_name=day_names[optimal_dow],
        optimal_days_before_due=optimal_lead,
        activity_by_day=activity,
        avg_payment_lead_days=round(avg_lead, 1),
        confidence=confidence,
    )


def suggest_reminder_time(user_id: int, due_date: date) -> date:
    """Suggest when to send a reminder for a specific due date."""
    timing = analyze_timing(user_id)
    lead = timing["optimal_days_before_due"]

    suggested = due_date - timedelta(days=lead)

    # Adjust to optimal day of week if within ±2 days
    dow = timing["optimal_day_of_week"]
    current_dow = suggested.weekday()
    diff = dow - current_dow
    if abs(diff) <= 2:
        suggested = suggested + timedelta(days=diff)

    # Don't suggest a date in the past
    if suggested < date.today():
        suggested = date.today()

    # Don't suggest after due date
    if suggested > due_date:
        suggested = due_date - timedelta(days=1)

    return suggested


def _get_activity_by_day(user_id: int, cutoff: date) -> dict[int, int]:
    """Count expenses per day of week."""
    expenses = (
        db.session.query(Expense.spent_at)
        .filter(Expense.user_id == user_id, Expense.spent_at >= cutoff)
        .all()
    )
    counter: Counter = Counter()
    for (d,) in expenses:
        counter[d.weekday()] += 1
    return dict(counter)


def _get_payment_lead_days(user_id: int, cutoff: date) -> list[float]:
    """Calculate how many days before due date bills are typically paid."""
    bills = db.session.query(Bill).filter_by(user_id=user_id).all()
    leads = []

    for bill in bills:
        # Find expenses that match this bill (same amount, near due date)
        related = (
            db.session.query(Expense)
            .filter(
                Expense.user_id == user_id,
                Expense.amount == bill.amount,
                Expense.spent_at >= cutoff,
            )
            .all()
        )
        for exp in related:
            if bill.next_due_date:
                delta = (bill.next_due_date - exp.spent_at).days
                if 0 <= delta <= 30:
                    leads.append(float(delta))

    return leads
