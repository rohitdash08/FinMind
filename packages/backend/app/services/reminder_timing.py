from __future__ import annotations

import statistics
from datetime import date, timedelta, datetime
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func

from app.models import Transaction, Reminder
from app import db


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OptimizedReminder:
    reminder_id: int
    current_reminder_days_before: int  # current lead time
    suggested_days_before: int         # optimized lead time
    reasoning: str
    confidence: float


@dataclass
class ReminderTimingResult:
    optimized_reminders: list[OptimizedReminder]
    general_recommendation: str
    avg_days_before_payment: float   # how many days before due date user typically pays
    on_time_rate: float             # % of bills paid on/before due date
    summary: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_date(d) -> Optional[date]:
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d))
    except (ValueError, AttributeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

def get_optimized_reminder_timing(
    user_id: int,
    months: int = 3,
) -> ReminderTimingResult:
    """
    Analyze payment behavior to suggest optimal reminder timing.

    Logic:
    - Look at recurring bill transactions (expenses) and their category/amount patterns
    - Estimate typical payment lead time from historical data
    - For reminders, suggest lead time = (avg days before payment) + 1-2 day buffer
    """
    months = max(1, min(12, months))
    cutoff = date.today() - timedelta(days=months * 31)

    # Try to query Reminder model; fall back gracefully if table doesn't exist
    try:
        reminders = (
            db.session.query(Reminder)
            .filter(Reminder.user_id == user_id)
            .all()
        )
    except Exception:
        reminders = []

    # Analyze transaction timing
    try:
        txs = (
            db.session.query(Transaction)
            .filter(
                Transaction.user_id == user_id,
                Transaction.date >= cutoff,
                Transaction.type == "expense",
            )
            .all()
        )
    except Exception:
        txs = []

    if not txs and not reminders:
        return ReminderTimingResult(
            optimized_reminders=[],
            general_recommendation="3 days before due date is a safe default.",
            avg_days_before_payment=3.0,
            on_time_rate=1.0,
            summary="No transaction or reminder data available for analysis.",
        )

    # Calculate payment day-of-month distribution from expense transactions
    payment_days = [_safe_date(tx.date).day for tx in txs if _safe_date(tx.date)]
    today = date.today()

    # Estimate avg days before end-of-month (proxy for bill due dates)
    days_from_eom = []
    for tx in txs:
        d = _safe_date(tx.date)
        if not d:
            continue
        # Last day of that month
        if d.month == 12:
            eom = date(d.year + 1, 1, 1) - timedelta(days=1)
        else:
            eom = date(d.year, d.month + 1, 1) - timedelta(days=1)
        days_from_eom.append((eom - d).days)

    avg_days_before = round(statistics.mean(days_from_eom), 1) if days_from_eom else 3.0

    # Simple on-time heuristic: payments before the 28th = likely on time
    on_time_count = sum(1 for d in payment_days if d <= 28)
    on_time_rate = round(on_time_count / len(payment_days), 2) if payment_days else 1.0

    # Optimize reminders
    optimized = []
    for reminder in reminders:
        current_days = getattr(reminder, 'days_before', 3) or 3

        # If paying early (avg_days_before > 7), suggest 5 days lead time
        # If paying late (avg_days_before < 3), suggest 7 days lead time
        if avg_days_before >= 7:
            suggested = 5
            reason = f"You typically pay {avg_days_before:.0f} days early. 5-day reminder is sufficient."
        elif avg_days_before <= 2:
            suggested = 7
            reason = "Payment history shows tight timing. 7-day reminder gives more buffer."
        else:
            suggested = max(3, round(avg_days_before))
            reason = f"Based on your payment patterns ({avg_days_before:.1f} days avg), {suggested} days is optimal."

        confidence = 0.7 if len(payment_days) >= 5 else 0.5

        optimized.append(
            OptimizedReminder(
                reminder_id=reminder.id,
                current_reminder_days_before=current_days,
                suggested_days_before=suggested,
                reasoning=reason,
                confidence=confidence,
            )
        )

    # General recommendation
    if avg_days_before >= 7:
        general_rec = "You're an early payer. A 5-day reminder window works well for you."
    elif avg_days_before <= 2:
        general_rec = "Consider setting reminders 7 days in advance to avoid late payments."
    else:
        general_rec = f"Based on your history, a {max(3, round(avg_days_before))}-day reminder is recommended."

    if not optimized:
        summary = (
            f"No active reminders to optimize. General recommendation: {general_rec} "
            f"(on-time payment rate: {on_time_rate*100:.0f}%)."
        )
    else:
        summary = (
            f"Optimized {len(optimized)} reminder(s) based on your payment patterns. "
            f"On-time rate: {on_time_rate*100:.0f}%."
        )

    return ReminderTimingResult(
        optimized_reminders=optimized,
        general_recommendation=general_rec,
        avg_days_before_payment=avg_days_before,
        on_time_rate=on_time_rate,
        summary=summary,
    )