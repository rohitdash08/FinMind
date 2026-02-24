"""Detect subscription cost increases by comparing recurring charges over time.

Groups expenses by merchant (notes) and currency, then checks whether the
most recent charge is higher than the previous one.  Only merchants with at
least ``min_history`` charges are considered.
"""

from __future__ import annotations

from datetime import date
from typing import List

from sqlalchemy import func

from ..extensions import db
from ..models import Expense


def detect_cost_increases(
    user_id: int,
    *,
    min_history: int = 2,
) -> List[dict]:
    """Return a list of merchants whose most recent charge increased.

    Each entry contains:
        merchant       – expense description (notes)
        currency       – currency code
        previous_amount – the charge before the latest
        current_amount  – the latest charge
        increase        – absolute increase
        increase_pct    – percentage increase
        previous_date   – date of the previous charge
        current_date    – date of the latest charge
    """

    # Find merchants with enough history
    merchants = (
        db.session.query(
            Expense.notes,
            Expense.currency,
            func.count(Expense.id).label("cnt"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.notes.isnot(None),
            Expense.notes != "",
        )
        .group_by(Expense.notes, Expense.currency)
        .having(func.count(Expense.id) >= min_history)
        .all()
    )

    results: List[dict] = []

    for notes, currency, _cnt in merchants:
        # Get the two most recent charges for this merchant
        recent = (
            db.session.query(Expense.amount, Expense.spent_at)
            .filter(
                Expense.user_id == user_id,
                Expense.notes == notes,
                Expense.currency == currency,
            )
            .order_by(Expense.spent_at.desc())
            .limit(2)
            .all()
        )

        if len(recent) < 2:
            continue

        current_amount, current_date = recent[0]
        previous_amount, previous_date = recent[1]

        current_f = float(current_amount)
        previous_f = float(previous_amount)

        if current_f <= previous_f:
            continue

        increase = round(current_f - previous_f, 2)
        increase_pct = round((increase / previous_f) * 100, 2) if previous_f > 0 else 0.0

        results.append(
            {
                "merchant": notes,
                "currency": currency,
                "previous_amount": previous_f,
                "current_amount": current_f,
                "increase": increase,
                "increase_pct": increase_pct,
                "previous_date": previous_date.isoformat() if isinstance(previous_date, date) else str(previous_date),
                "current_date": current_date.isoformat() if isinstance(current_date, date) else str(current_date),
            }
        )

    return results
