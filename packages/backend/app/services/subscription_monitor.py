"""Subscription cost increase detection service.

Monitors recurring expenses for price changes over time and alerts
users when subscription costs increase. Tracks historical amounts
per recurring expense to identify trends.

Detection logic:
1. Groups expenses by recurring source.
2. Orders by date and compares consecutive amounts.
3. Flags increases with context (absolute + percentage change).
4. Provides a cost trend summary per subscription.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TypedDict

from sqlalchemy import func

from ..extensions import db
from ..models import Expense, RecurringExpense

logger = logging.getLogger("finmind.subscription_monitor")


class CostChange(TypedDict):
    recurring_id: int
    name: str
    currency: str
    previous_amount: float
    new_amount: float
    change_absolute: float
    change_percent: float
    detected_on: str
    first_seen: str


class SubscriptionTrend(TypedDict):
    recurring_id: int
    name: str
    currency: str
    current_amount: float
    original_amount: float
    total_increase: float
    total_increase_percent: float
    change_count: int
    history: list[dict]


def detect_cost_increases(
    user_id: int,
    lookback_days: int = 365,
    min_change_percent: float = 0.5,
) -> list[CostChange]:
    """Find all subscription/recurring cost increases for a user.

    Args:
        user_id: The user to check.
        lookback_days: How far back to look.
        min_change_percent: Minimum % increase to flag (default 0.5%).

    Returns:
        List of cost changes sorted by detection date (newest first).
    """
    changes: list[CostChange] = []
    cutoff = date.today() - timedelta(days=lookback_days)

    recurring = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    for rec in recurring:
        expenses = (
            db.session.query(Expense)
            .filter(
                Expense.user_id == user_id,
                Expense.source_recurring_id == rec.id,
                Expense.spent_at >= cutoff,
            )
            .order_by(Expense.spent_at.asc())
            .all()
        )

        if len(expenses) < 2:
            continue

        prev = expenses[0]
        for exp in expenses[1:]:
            prev_amt = float(prev.amount)
            curr_amt = float(exp.amount)

            if prev_amt <= 0:
                prev = exp
                continue

            change_pct = ((curr_amt - prev_amt) / prev_amt) * 100

            if change_pct > min_change_percent:
                changes.append(
                    CostChange(
                        recurring_id=rec.id,
                        name=rec.notes,
                        currency=exp.currency,
                        previous_amount=prev_amt,
                        new_amount=curr_amt,
                        change_absolute=round(curr_amt - prev_amt, 2),
                        change_percent=round(change_pct, 2),
                        detected_on=exp.spent_at.isoformat(),
                        first_seen=prev.spent_at.isoformat(),
                    )
                )

            prev = exp

    changes.sort(key=lambda c: c["detected_on"], reverse=True)
    logger.info(
        "Subscription cost check user=%s: %d increases found", user_id, len(changes)
    )
    return changes


def get_subscription_trends(
    user_id: int, lookback_days: int = 365
) -> list[SubscriptionTrend]:
    """Build a cost trend summary for each recurring subscription.

    Shows the trajectory of each subscription's cost over time,
    including total increase from original price.
    """
    trends: list[SubscriptionTrend] = []
    cutoff = date.today() - timedelta(days=lookback_days)

    recurring = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    for rec in recurring:
        expenses = (
            db.session.query(Expense)
            .filter(
                Expense.user_id == user_id,
                Expense.source_recurring_id == rec.id,
                Expense.spent_at >= cutoff,
            )
            .order_by(Expense.spent_at.asc())
            .all()
        )

        if not expenses:
            continue

        history = []
        change_count = 0
        prev_amount = None

        for exp in expenses:
            amt = float(exp.amount)
            entry = {"date": exp.spent_at.isoformat(), "amount": amt}

            if prev_amount is not None and amt != prev_amount:
                entry["change"] = round(amt - prev_amount, 2)
                entry["change_percent"] = (
                    round(((amt - prev_amount) / prev_amount) * 100, 2)
                    if prev_amount > 0
                    else 0
                )
                if amt > prev_amount:
                    change_count += 1
            history.append(entry)
            prev_amount = amt

        original = float(expenses[0].amount)
        current = float(expenses[-1].amount)
        total_increase = round(current - original, 2)
        total_pct = (
            round((total_increase / original) * 100, 2) if original > 0 else 0
        )

        trends.append(
            SubscriptionTrend(
                recurring_id=rec.id,
                name=rec.notes,
                currency=rec.currency,
                current_amount=current,
                original_amount=original,
                total_increase=total_increase,
                total_increase_percent=total_pct,
                change_count=change_count,
                history=history,
            )
        )

    # Sort by total increase descending (biggest increases first)
    trends.sort(key=lambda t: t["total_increase"], reverse=True)
    return trends
