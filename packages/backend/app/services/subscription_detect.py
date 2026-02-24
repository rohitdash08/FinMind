"""Auto-detect subscriptions from recurring charges in expense history.

Scans a user's expenses looking for repeated (merchant, amount) pairs that
recur on a roughly monthly cadence.  A charge is considered a likely
subscription when it appears at least ``min_occurrences`` times with
consecutive gaps within ``tolerance_days`` of 30 days.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import List

from sqlalchemy import func

from ..extensions import db
from ..models import Expense


def detect_subscriptions(
    user_id: int,
    *,
    min_occurrences: int = 3,
    tolerance_days: int = 5,
) -> List[dict]:
    """Return a list of detected subscription-like charges.

    Each entry contains:
        merchant   – the expense description (notes)
        amount     – the recurring amount
        currency   – currency code
        occurrences – how many times the charge appeared
        first_seen – earliest date
        last_seen  – latest date
        cadence    – estimated cadence label (e.g. "MONTHLY")
    """

    # Group expenses by (notes, amount, currency) with at least min_occurrences
    groups = (
        db.session.query(
            Expense.notes,
            Expense.amount,
            Expense.currency,
            func.count(Expense.id).label("cnt"),
            func.min(Expense.spent_at).label("first_seen"),
            func.max(Expense.spent_at).label("last_seen"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.notes.isnot(None),
            Expense.notes != "",
        )
        .group_by(Expense.notes, Expense.amount, Expense.currency)
        .having(func.count(Expense.id) >= min_occurrences)
        .all()
    )

    results: List[dict] = []

    for notes, amount, currency, cnt, first_seen, last_seen in groups:
        # Fetch individual dates to verify cadence
        dates = [
            row[0]
            for row in db.session.query(Expense.spent_at)
            .filter(
                Expense.user_id == user_id,
                Expense.notes == notes,
                Expense.amount == amount,
                Expense.currency == currency,
            )
            .order_by(Expense.spent_at)
            .all()
        ]

        cadence = _estimate_cadence(dates, tolerance_days)
        if cadence is None:
            continue

        results.append(
            {
                "merchant": notes,
                "amount": float(amount),
                "currency": currency,
                "occurrences": cnt,
                "first_seen": first_seen.isoformat() if isinstance(first_seen, date) else str(first_seen),
                "last_seen": last_seen.isoformat() if isinstance(last_seen, date) else str(last_seen),
                "cadence": cadence,
            }
        )

    return results


def _estimate_cadence(dates: list[date], tolerance: int) -> str | None:
    """Return a cadence label if consecutive gaps are consistent, else None."""
    if len(dates) < 2:
        return None

    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    avg_gap = sum(gaps) / len(gaps)

    cadence_map = [
        ("WEEKLY", 7),
        ("MONTHLY", 30),
        ("YEARLY", 365),
    ]

    for label, expected in cadence_map:
        if all(abs(g - expected) <= tolerance for g in gaps):
            return label

    # Fallback: check if average gap is close to monthly
    if abs(avg_gap - 30) <= tolerance:
        return "MONTHLY"

    return None
