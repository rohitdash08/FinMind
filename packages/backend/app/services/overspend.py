"""Category overspend early warning system."""

from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Expense, Category
import logging

logger = logging.getLogger("finmind.overspend")


def detect_overspend(user_id: int, lookback_weeks: int = 4) -> list[dict]:
    """Detect categories where current week spending exceeds historical average.

    Compares this week's spending per category against the average of
    the previous N weeks. Flags categories exceeding 120% of average.
    """
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    history_start = week_start - timedelta(weeks=lookback_weeks)

    # Current week spending by category
    current_expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= week_start,
            Expense.spent_at <= today,
        )
        .all()
    )

    current_by_cat: dict[int, Decimal] = {}
    for e in current_expenses:
        cat_id = e.category_id or 0
        current_by_cat.setdefault(cat_id, Decimal("0"))
        current_by_cat[cat_id] += Decimal(str(e.amount))

    # Historical weekly average by category
    history_expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= history_start,
            Expense.spent_at < week_start,
        )
        .all()
    )

    history_by_cat: dict[int, Decimal] = {}
    for e in history_expenses:
        cat_id = e.category_id or 0
        history_by_cat.setdefault(cat_id, Decimal("0"))
        history_by_cat[cat_id] += Decimal(str(e.amount))

    # Calculate weekly averages
    warnings = []
    for cat_id, current_total in current_by_cat.items():
        hist_total = history_by_cat.get(cat_id, Decimal("0"))
        weekly_avg = hist_total / lookback_weeks if lookback_weeks > 0 else Decimal("0")

        if weekly_avg > 0:
            ratio = float(current_total / weekly_avg)
            if ratio >= 1.2:  # 120% of average
                cat = db.session.get(Category, cat_id) if cat_id else None
                warnings.append({
                    "category_id": cat_id,
                    "category_name": cat.name if cat else "Uncategorized",
                    "current_week": float(current_total),
                    "weekly_average": float(weekly_avg),
                    "overspend_ratio": round(ratio, 2),
                    "overspend_percent": round((ratio - 1) * 100, 1),
                })

    return sorted(warnings, key=lambda w: -w["overspend_ratio"])
