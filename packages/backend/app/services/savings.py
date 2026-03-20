"""Savings opportunity detection engine.

Analyses a user's spending history and returns actionable savings
opportunities based on four detection rules:

1. Month-over-month category increases
2. High-frequency small purchases (latte factor)
3. Subscription/recurring duplicates
4. Above-average category spending
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.savings")

# --- thresholds --------------------------------------------------------
MOM_INCREASE_PCT = 20  # flag category if spending rose >= 20 %
SMALL_PURCHASE_THRESHOLD = 10.0  # amounts <= this are "small"
SMALL_PURCHASE_MIN_COUNT = 8  # need at least this many in a month
ABOVE_AVG_FACTOR = 1.30  # flag category if > 130 % of 3-month average


def detect_savings_opportunities(
    user_id: int,
    month: str | None = None,
) -> list[dict]:
    """Return a list of savings-opportunity dicts for *month* (YYYY-MM).

    Each dict carries:
        type        – rule identifier
        title       – short human-readable title
        description – actionable message
        potential_savings – estimated dollar amount
        category    – category name (or None)
        trend       – contextual numbers for the frontend
    """
    ym = (month or date.today().strftime("%Y-%m")).strip()
    year, mon = map(int, ym.split("-"))

    opportunities: list[dict] = []

    opportunities.extend(_detect_mom_increases(user_id, year, mon))
    opportunities.extend(_detect_latte_factor(user_id, year, mon))
    opportunities.extend(_detect_duplicate_subscriptions(user_id, year, mon))
    opportunities.extend(_detect_above_average(user_id, year, mon))

    # Sort by potential savings descending
    opportunities.sort(key=lambda o: o["potential_savings"], reverse=True)
    logger.info(
        "Detected %d savings opportunities for user=%s month=%s",
        len(opportunities),
        user_id,
        ym,
    )
    return opportunities


# --- rule implementations -----------------------------------------------


def _category_totals(user_id: int, year: int, month: int) -> dict[int, float]:
    """Return {category_id: total_spend} for one month (expenses only)."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
            Expense.category_id.isnot(None),
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {int(cid): float(total) for cid, total in rows}


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _category_name(category_id: int) -> str:
    cat = db.session.get(Category, category_id)
    return cat.name if cat else f"Category #{category_id}"


def _detect_mom_increases(
    user_id: int, year: int, month: int
) -> list[dict]:
    """Flag categories where spending increased >= MOM_INCREASE_PCT."""
    current = _category_totals(user_id, year, month)
    py, pm = _prev_month(year, month)
    previous = _category_totals(user_id, py, pm)

    results: list[dict] = []
    for cid, cur_total in current.items():
        prev_total = previous.get(cid, 0)
        if prev_total <= 0:
            continue
        pct = ((cur_total - prev_total) / prev_total) * 100
        if pct >= MOM_INCREASE_PCT:
            savings = round(cur_total - prev_total, 2)
            name = _category_name(cid)
            results.append(
                {
                    "type": "month_over_month_increase",
                    "title": f"{name} spending spike",
                    "description": (
                        f"Your {name} spending increased {pct:.0f}% this month. "
                        f"Returning to last month's level could save you "
                        f"${savings:,.2f}."
                    ),
                    "potential_savings": savings,
                    "category": name,
                    "trend": {
                        "current_month": round(cur_total, 2),
                        "previous_month": round(prev_total, 2),
                        "change_pct": round(pct, 1),
                    },
                }
            )
    return results


def _detect_latte_factor(
    user_id: int, year: int, month: int
) -> list[dict]:
    """Flag high-frequency small purchases that add up."""
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
            Expense.amount <= SMALL_PURCHASE_THRESHOLD,
        )
        .all()
    )
    if len(rows) < SMALL_PURCHASE_MIN_COUNT:
        return []

    total = sum(float(e.amount) for e in rows)
    # Group by category for a richer message
    by_cat: dict[int | None, float] = defaultdict(float)
    for e in rows:
        by_cat[e.category_id] += float(e.amount)

    top_cat_id = max(by_cat, key=lambda k: by_cat[k])  # type: ignore[arg-type]
    top_cat_name = _category_name(top_cat_id) if top_cat_id else "Uncategorized"

    half = round(total / 2, 2)
    return [
        {
            "type": "high_frequency_small_purchases",
            "title": "Small purchases add up",
            "description": (
                f"You made {len(rows)} small purchases (under "
                f"${SMALL_PURCHASE_THRESHOLD:.0f}) totalling ${total:,.2f} "
                f"this month, mostly in {top_cat_name}. Cutting these in half "
                f"would save ${half:,.2f}."
            ),
            "potential_savings": half,
            "category": top_cat_name,
            "trend": {
                "transaction_count": len(rows),
                "total_amount": round(total, 2),
            },
        }
    ]


def _detect_duplicate_subscriptions(
    user_id: int, year: int, month: int
) -> list[dict]:
    """Flag notes that appear more than once with the same amount (likely duplicate subs)."""
    rows = (
        db.session.query(
            Expense.notes,
            Expense.amount,
            func.count(Expense.id),
        )
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
            Expense.notes.isnot(None),
            Expense.notes != "",
        )
        .group_by(Expense.notes, Expense.amount)
        .having(func.count(Expense.id) > 1)
        .all()
    )

    results: list[dict] = []
    for notes, amount, count in rows:
        dup_cost = round(float(amount) * (count - 1), 2)
        results.append(
            {
                "type": "subscription_duplicate",
                "title": f"Possible duplicate: {notes}",
                "description": (
                    f'"{notes}" (${float(amount):,.2f}) appears {count} times '
                    f"this month. If duplicated, you could save ${dup_cost:,.2f}."
                ),
                "potential_savings": dup_cost,
                "category": None,
                "trend": {
                    "occurrences": count,
                    "unit_amount": round(float(amount), 2),
                },
            }
        )
    return results


def _detect_above_average(
    user_id: int, year: int, month: int
) -> list[dict]:
    """Flag categories spending > ABOVE_AVG_FACTOR of their 3-month average."""
    current = _category_totals(user_id, year, month)
    if not current:
        return []

    # Compute 3-month rolling average (the 3 months *before* current)
    averages: dict[int, float] = defaultdict(float)
    counts: Counter[int] = Counter()
    y, m = year, month
    for _ in range(3):
        y, m = _prev_month(y, m)
        totals = _category_totals(user_id, y, m)
        for cid, val in totals.items():
            averages[cid] += val
            counts[cid] += 1

    results: list[dict] = []
    for cid, cur_total in current.items():
        if counts[cid] < 2:
            # need at least 2 months of history to be meaningful
            continue
        avg = averages[cid] / counts[cid]
        if avg <= 0:
            continue
        if cur_total > avg * ABOVE_AVG_FACTOR:
            savings = round(cur_total - avg, 2)
            name = _category_name(cid)
            results.append(
                {
                    "type": "above_average_spending",
                    "title": f"{name} above your average",
                    "description": (
                        f"You spent ${cur_total:,.2f} on {name} this month, "
                        f"which is {cur_total / avg:.1f}x your "
                        f"{counts[cid]}-month average of ${avg:,.2f}. "
                        f"Returning to average could save ${savings:,.2f}."
                    ),
                    "potential_savings": savings,
                    "category": name,
                    "trend": {
                        "current_month": round(cur_total, 2),
                        "rolling_average": round(avg, 2),
                        "months_in_average": counts[cid],
                    },
                }
            )
    return results
