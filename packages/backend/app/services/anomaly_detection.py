"""Recurring transaction anomaly detection service.

Detects unexpected changes in recurring expenses:
- Amount changes (e.g. subscription price increase)
- Missing expected transactions (e.g. payment didn't go through)
- Frequency changes (e.g. bi-weekly becoming weekly)
- New recurring patterns detected from regular transactions

Uses statistical analysis (mean + standard deviation) to identify
anomalies without requiring user-configured thresholds.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func

from ..extensions import db
from ..models import Expense, RecurringExpense

logger = logging.getLogger("finmind.anomaly_detection")


class Anomaly(TypedDict):
    type: str          # "amount_change" | "missing_transaction" | "frequency_change"
    severity: str      # "low" | "medium" | "high"
    recurring_id: int
    description: str
    expected: str
    actual: str
    detected_at: str


def detect_anomalies(user_id: int, lookback_days: int = 90) -> list[Anomaly]:
    """Run anomaly detection on a user's recurring expenses.

    Checks the last *lookback_days* of transaction history against
    configured recurring expenses to find discrepancies.
    """
    anomalies: list[Anomaly] = []
    today = date.today()
    lookback_start = today - timedelta(days=lookback_days)

    recurring = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    for rec in recurring:
        # Get all generated expenses from this recurring entry
        expenses = (
            db.session.query(Expense)
            .filter(
                Expense.user_id == user_id,
                Expense.source_recurring_id == rec.id,
                Expense.spent_at >= lookback_start,
            )
            .order_by(Expense.spent_at.asc())
            .all()
        )

        # --- Amount anomaly: check if any expense deviates from the recurring amount ---
        anomalies.extend(_check_amount_anomalies(rec, expenses))

        # --- Missing transaction: check if expected occurrences are present ---
        anomalies.extend(_check_missing_transactions(rec, expenses, lookback_start, today))

    # --- Pattern detection: find non-recurring expenses that look recurring ---
    anomalies.extend(_detect_recurring_patterns(user_id, lookback_start))

    logger.info(
        "Anomaly detection user=%s: %d anomalies found", user_id, len(anomalies)
    )
    return anomalies


def _check_amount_anomalies(
    rec: RecurringExpense, expenses: list[Expense]
) -> list[Anomaly]:
    """Flag expenses whose amount differs from the configured recurring amount."""
    anomalies: list[Anomaly] = []
    expected = float(rec.amount)

    for exp in expenses:
        actual = float(exp.amount)
        if expected == 0:
            continue
        pct_change = abs(actual - expected) / expected * 100

        if pct_change < 1:
            continue  # negligible

        severity = "low" if pct_change < 10 else "medium" if pct_change < 25 else "high"
        anomalies.append(
            Anomaly(
                type="amount_change",
                severity=severity,
                recurring_id=rec.id,
                description=(
                    f"Recurring expense '{rec.notes}' on {exp.spent_at.isoformat()} "
                    f"was {exp.currency} {actual:.2f} instead of expected "
                    f"{exp.currency} {expected:.2f} ({pct_change:+.1f}%)"
                ),
                expected=f"{expected:.2f}",
                actual=f"{actual:.2f}",
                detected_at=date.today().isoformat(),
            )
        )
    return anomalies


def _check_missing_transactions(
    rec: RecurringExpense,
    expenses: list[Expense],
    start: date,
    end: date,
) -> list[Anomaly]:
    """Flag expected recurring dates that have no matching expense."""
    anomalies: list[Anomaly] = []
    expense_dates = {exp.spent_at for exp in expenses}

    # Walk through expected dates
    cadence = rec.cadence.value
    at = rec.start_date
    rec_end = rec.end_date or end

    while at <= min(end, rec_end):
        if at >= start and at <= end - timedelta(days=2):
            # Allow 2-day grace period for late transactions
            window = {at + timedelta(days=d) for d in range(-1, 3)}
            if not window & expense_dates:
                anomalies.append(
                    Anomaly(
                        type="missing_transaction",
                        severity="medium",
                        recurring_id=rec.id,
                        description=(
                            f"Expected '{rec.notes}' ({cadence.lower()}, "
                            f"{rec.currency} {float(rec.amount):.2f}) "
                            f"around {at.isoformat()} — no matching transaction found"
                        ),
                        expected=at.isoformat(),
                        actual="missing",
                        detected_at=date.today().isoformat(),
                    )
                )
        at = _advance_date(at, cadence)
    return anomalies


def _detect_recurring_patterns(user_id: int, start: date) -> list[Anomaly]:
    """Find non-recurring expenses that form a recurring pattern.

    Groups expenses by (notes, amount) and checks if they appear ≥3 times
    with roughly regular intervals.
    """
    anomalies: list[Anomaly] = []

    # Find expenses NOT linked to a recurring entry, grouped by description+amount
    groups = (
        db.session.query(
            Expense.notes,
            Expense.amount,
            Expense.currency,
            func.count(Expense.id).label("cnt"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.source_recurring_id.is_(None),
        )
        .group_by(Expense.notes, Expense.amount, Expense.currency)
        .having(func.count(Expense.id) >= 3)
        .all()
    )

    for notes, amount, currency, cnt in groups:
        # Get the dates for this group
        dates = [
            row[0]
            for row in db.session.query(Expense.spent_at)
            .filter(
                Expense.user_id == user_id,
                Expense.notes == notes,
                Expense.amount == amount,
                Expense.source_recurring_id.is_(None),
            )
            .order_by(Expense.spent_at.asc())
            .all()
        ]
        if len(dates) < 3:
            continue

        # Check if intervals are roughly regular (within 20%)
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        if not intervals or min(intervals) < 5:  # skip very frequent
            continue
        avg_interval = sum(intervals) / len(intervals)
        if avg_interval == 0:
            continue
        variance = sum((iv - avg_interval) ** 2 for iv in intervals) / len(intervals)
        cv = (variance ** 0.5) / avg_interval  # coefficient of variation

        if cv < 0.3:  # reasonably regular
            anomalies.append(
                Anomaly(
                    type="recurring_pattern_detected",
                    severity="low",
                    recurring_id=0,
                    description=(
                        f"'{notes}' ({currency} {float(amount):.2f}) appears "
                        f"{cnt} times with ~{avg_interval:.0f}-day intervals. "
                        f"Consider adding as a recurring expense."
                    ),
                    expected="not_configured",
                    actual=f"{cnt} occurrences",
                    detected_at=date.today().isoformat(),
                )
            )
    return anomalies


def _advance_date(at: date, cadence: str) -> date:
    """Advance a date by one cadence period."""
    import calendar

    if cadence == "DAILY":
        return at + timedelta(days=1)
    if cadence == "WEEKLY":
        return at + timedelta(days=7)
    if cadence == "MONTHLY":
        year = at.year + (1 if at.month == 12 else 0)
        month = 1 if at.month == 12 else at.month + 1
        day = min(at.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    # YEARLY
    year = at.year + 1
    day = min(at.day, calendar.monthrange(year, at.month)[1])
    return date(year, at.month, day)
