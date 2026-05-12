"""Recurring transaction anomaly alerts."""

from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import RecurringExpense, Expense
import logging

logger = logging.getLogger("finmind.recurring_anomaly")


def detect_recurring_anomalies(user_id: int) -> list[dict]:
    """Detect anomalies in recurring transactions.

    Checks for:
    1. Missed recurring charges (expected but not found)
    2. Amount changes in recurring expenses
    3. Duplicate charges (charged more than expected frequency)
    """
    anomalies = []
    today = date.today()

    recurring = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    for rec in recurring:
        recent_expenses = (
            db.session.query(Expense)
            .filter(
                Expense.user_id == user_id,
                Expense.source_recurring_id == rec.id,
                Expense.spent_at >= today - timedelta(days=60),
            )
            .order_by(Expense.spent_at.desc())
            .all()
        )

        expected_amount = Decimal(str(rec.amount))

        # Check for amount changes
        for exp in recent_expenses:
            actual = Decimal(str(exp.amount))
            if expected_amount > 0:
                diff_pct = abs(float((actual - expected_amount) / expected_amount * 100))
                if diff_pct > 10:
                    anomalies.append({
                        "type": "amount_change",
                        "recurring_id": rec.id,
                        "name": rec.notes,
                        "expected_amount": float(expected_amount),
                        "actual_amount": float(actual),
                        "change_percent": round(diff_pct, 1),
                        "date": exp.spent_at.isoformat(),
                    })
                    break

        # Check for missed charges
        if not recent_expenses and rec.start_date <= today:
            days_since_start = (today - rec.start_date).days
            if rec.cadence.value == "MONTHLY" and days_since_start > 35:
                anomalies.append({
                    "type": "missed_charge",
                    "recurring_id": rec.id,
                    "name": rec.notes,
                    "expected_amount": float(expected_amount),
                    "last_expected": rec.start_date.isoformat(),
                })

        # Check for duplicate charges (more than expected in period)
        if rec.cadence.value == "MONTHLY" and len(recent_expenses) > 2:
            anomalies.append({
                "type": "duplicate_charge",
                "recurring_id": rec.id,
                "name": rec.notes,
                "expected_count": 2,
                "actual_count": len(recent_expenses),
                "total_charged": float(sum(Decimal(str(e.amount)) for e in recent_expenses)),
            })

    return anomalies
