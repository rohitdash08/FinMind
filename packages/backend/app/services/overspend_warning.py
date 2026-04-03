"""Category overspend early warning system.

Tracks spending per category against historical averages and
user-defined budgets. Generates warnings when spending pace
suggests a category will exceed its typical monthly amount.

Warning levels:
- "on_track": Spending pace is normal
- "caution": On pace to exceed average by 10-25%
- "warning": On pace to exceed average by 25-50%  
- "critical": On pace to exceed average by 50%+
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TypedDict

from sqlalchemy import func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.overspend_warning")


class CategoryWarning(TypedDict):
    category_id: int | None
    category_name: str
    level: str  # on_track | caution | warning | critical
    current_spend: float
    monthly_average: float
    projected_spend: float
    overspend_percent: float
    days_remaining: int
    currency: str


def check_overspend(user_id: int, reference_months: int = 3) -> list[CategoryWarning]:
    """Check all categories for potential overspending this month.

    Args:
        user_id: The user to analyze.
        reference_months: How many past months to use for the average.

    Returns:
        List of warnings sorted by severity (worst first).
    """
    today = date.today()
    month_start = date(today.year, today.month, 1)
    day_of_month = today.day
    days_in_month = _days_in_month(today.year, today.month)
    days_remaining = days_in_month - day_of_month

    # Avoid division by zero at month start
    if day_of_month < 1:
        day_of_month = 1

    # Get category names
    categories = {
        c.id: c.name
        for c in db.session.query(Category).filter_by(user_id=user_id).all()
    }

    # Current month spending per category
    current = (
        db.session.query(
            Expense.category_id,
            Expense.currency,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= month_start,
        )
        .group_by(Expense.category_id, Expense.currency)
        .all()
    )

    # Historical monthly averages per category
    hist_start = month_start - timedelta(days=reference_months * 31)
    historical = (
        db.session.query(
            Expense.category_id,
            Expense.currency,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= hist_start,
            Expense.spent_at < month_start,
        )
        .group_by(Expense.category_id, Expense.currency)
        .all()
    )

    hist_map: dict[tuple, float] = {}
    for row in historical:
        key = (row.category_id, row.currency)
        hist_map[key] = float(row.total or 0) / max(reference_months, 1)

    warnings: list[CategoryWarning] = []

    for row in current:
        key = (row.category_id, row.currency)
        current_spend = float(row.total or 0)
        monthly_avg = hist_map.get(key, 0)

        # Project spending for the full month based on current pace
        daily_pace = current_spend / day_of_month
        projected = daily_pace * days_in_month

        # Calculate overspend percentage vs historical average
        if monthly_avg > 0:
            overspend_pct = ((projected - monthly_avg) / monthly_avg) * 100
        elif projected > 0:
            overspend_pct = 100.0
        else:
            overspend_pct = 0.0

        # Determine warning level
        if overspend_pct >= 50:
            level = "critical"
        elif overspend_pct >= 25:
            level = "warning"
        elif overspend_pct >= 10:
            level = "caution"
        else:
            level = "on_track"

        warnings.append(
            CategoryWarning(
                category_id=row.category_id,
                category_name=categories.get(row.category_id, "Uncategorized")
                if row.category_id
                else "Uncategorized",
                level=level,
                current_spend=round(current_spend, 2),
                monthly_average=round(monthly_avg, 2),
                projected_spend=round(projected, 2),
                overspend_percent=round(overspend_pct, 2),
                days_remaining=days_remaining,
                currency=row.currency or "INR",
            )
        )

    # Sort: critical first, then warning, caution, on_track
    severity_order = {"critical": 0, "warning": 1, "caution": 2, "on_track": 3}
    warnings.sort(key=lambda w: (severity_order.get(w["level"], 4), -w["overspend_percent"]))

    logger.info("Overspend check user=%s: %d warnings", user_id, len(warnings))
    return warnings


def _days_in_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]
