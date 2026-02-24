"""Recurring transaction anomaly detection service.

Detects unusual amount changes in recurring expenses by comparing each
generated expense against the historical mean and standard deviation for
that recurring series.  An anomaly is flagged when the amount deviates
by more than a configurable number of standard deviations (default 2).
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import sqrt
from typing import List

from sqlalchemy import func

from ..extensions import db
from ..models import Expense, RecurringExpense

logger = logging.getLogger("finmind.anomaly")

# Default: flag amounts that deviate by more than 2 standard deviations
DEFAULT_SENSITIVITY = 2.0
# Minimum number of historical data points required before flagging
MIN_HISTORY = 3


@dataclass
class Anomaly:
    recurring_expense_id: int
    expense_id: int
    description: str
    expected_amount: float
    actual_amount: float
    deviation_pct: float
    spent_at: str
    severity: str  # "warning" | "critical"

    def to_dict(self) -> dict:
        return {
            "recurring_expense_id": self.recurring_expense_id,
            "expense_id": self.expense_id,
            "description": self.description,
            "expected_amount": self.expected_amount,
            "actual_amount": self.actual_amount,
            "deviation_pct": self.deviation_pct,
            "spent_at": self.spent_at,
            "severity": self.severity,
        }


def detect_anomalies(
    user_id: int,
    sensitivity: float = DEFAULT_SENSITIVITY,
    since: date | None = None,
) -> List[Anomaly]:
    """Scan all recurring expense series for the user and return anomalies.

    Args:
        user_id: owner of the recurring expenses
        sensitivity: number of std-devs before flagging (lower = more sensitive)
        since: only consider expenses on or after this date (default: all)

    Returns:
        list of Anomaly objects sorted by severity then date descending
    """
    recurring_items = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=user_id)
        .all()
    )

    anomalies: List[Anomaly] = []

    for rec in recurring_items:
        anomalies.extend(
            _check_series(rec, user_id, sensitivity, since)
        )

    # Sort: critical first, then by date descending
    severity_order = {"critical": 0, "warning": 1}
    anomalies.sort(
        key=lambda a: (severity_order.get(a.severity, 2), a.spent_at),
        reverse=False,
    )
    # Reverse date within same severity
    anomalies.sort(key=lambda a: severity_order.get(a.severity, 2))

    return anomalies


def _check_series(
    rec: RecurringExpense,
    user_id: int,
    sensitivity: float,
    since: date | None,
) -> List[Anomaly]:
    """Check a single recurring expense series for anomalies."""
    q = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.source_recurring_id == rec.id,
        )
        .order_by(Expense.spent_at.asc())
    )
    if since:
        q = q.filter(Expense.spent_at >= since)

    expenses = q.all()

    if len(expenses) < MIN_HISTORY:
        return []

    amounts = [float(e.amount) for e in expenses]
    anomalies: List[Anomaly] = []

    for i in range(MIN_HISTORY, len(expenses)):
        history = amounts[:i]
        current = amounts[i]
        expense = expenses[i]

        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std_dev = sqrt(variance) if variance > 0 else 0.0

        if std_dev == 0:
            # All previous amounts identical — flag if current differs
            if abs(current - mean) > 0.01:
                deviation_pct = (
                    round(abs(current - mean) / mean * 100, 1) if mean else 0.0
                )
                anomalies.append(
                    Anomaly(
                        recurring_expense_id=rec.id,
                        expense_id=expense.id,
                        description=rec.notes or "",
                        expected_amount=round(mean, 2),
                        actual_amount=round(current, 2),
                        deviation_pct=deviation_pct,
                        spent_at=expense.spent_at.isoformat(),
                        severity="critical" if deviation_pct > 50 else "warning",
                    )
                )
            continue

        z_score = abs(current - mean) / std_dev
        if z_score > sensitivity:
            deviation_pct = round(abs(current - mean) / mean * 100, 1) if mean else 0.0
            severity = "critical" if z_score > sensitivity * 1.5 else "warning"
            anomalies.append(
                Anomaly(
                    recurring_expense_id=rec.id,
                    expense_id=expense.id,
                    description=rec.notes or "",
                    expected_amount=round(mean, 2),
                    actual_amount=round(current, 2),
                    deviation_pct=deviation_pct,
                    spent_at=expense.spent_at.isoformat(),
                    severity=severity,
                )
            )

    return anomalies
