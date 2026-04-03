"""
Spending Trend Heatmap Visualization (#116)
Generates heatmap data showing spending intensity across time dimensions.
Supports: daily-by-week, day-of-week, hour-of-day, monthly aggregations.
"""
from datetime import date, timedelta
from typing import Any
from decimal import Decimal
from ..extensions import db
from ..models import Expense, Category


def _week_number(d: date) -> int:
    """Return ISO week number for a date."""
    return d.isocalendar()[1]


def _intensity(value: float, max_value: float) -> str:
    """Convert a value to intensity level (0-4, like GitHub contribution graph)."""
    if max_value == 0 or value == 0:
        return "0"
    ratio = value / max_value
    if ratio <= 0.25:
        return "1"
    elif ratio <= 0.5:
        return "2"
    elif ratio <= 0.75:
        return "3"
    return "4"


def get_spending_heatmap(
    user_id: int,
    months: int = 6,
    view: str = "daily",
) -> dict[str, Any]:
    """
    Generate spending heatmap data for visualization.

    Args:
        user_id: The user ID to analyze
        months: Number of months of data to include (1-12)
        view: 'daily' (365-day grid), 'weekday' (Mon-Sun aggregation),
              'monthly' (month-by-month)

    Returns:
        Heatmap data with cells, max_value, and metadata
    """
    months = min(12, max(1, months))
    today = date.today()
    start_date = today - timedelta(days=30 * months)

    rows = (
        db.session.query(
            Expense.amount,
            Expense.spent_at,
            Category.name.label("category_name"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start_date,
            Expense.spent_at <= today,
        )
        .all()
    )

    if not rows:
        return _empty_heatmap(view, months)

    # Aggregate by date
    by_date: dict[date, float] = {}
    for r in rows:
        by_date[r.spent_at] = by_date.get(r.spent_at, 0.0) + float(r.amount)

    if view == "weekday":
        return _weekday_heatmap(by_date, months)
    elif view == "monthly":
        return _monthly_heatmap(by_date, months, start_date, today)
    else:  # "daily" default
        return _daily_heatmap(by_date, start_date, today, months)


def _daily_heatmap(
    by_date: dict[date, float],
    start_date: date,
    end_date: date,
    months: int,
) -> dict[str, Any]:
    """Generate a daily grid heatmap (like GitHub contributions)."""
    max_val = max(by_date.values()) if by_date else 0

    cells = []
    current = start_date
    while current <= end_date:
        amount = by_date.get(current, 0.0)
        cells.append({
            "date": current.isoformat(),
            "day_of_week": current.weekday(),  # 0=Mon, 6=Sun
            "week": _week_number(current),
            "month": current.month,
            "amount": round(amount, 2),
            "intensity": _intensity(amount, max_val),
        })
        current += timedelta(days=1)

    total_spend = sum(by_date.values())
    active_days = sum(1 for v in by_date.values() if v > 0)

    return {
        "view": "daily",
        "cells": cells,
        "max_value": round(max_val, 2),
        "total_spend": round(total_spend, 2),
        "active_days": active_days,
        "total_days": len(cells),
        "months_analyzed": months,
        "intensity_scale": {
            "0": "No spending",
            "1": f"Low (up to {max_val * 0.25:.0f})",
            "2": f"Medium (up to {max_val * 0.5:.0f})",
            "3": f"High (up to {max_val * 0.75:.0f})",
            "4": f"Very High (up to {max_val:.0f})",
        },
        "summary": (
            f"{active_days} spending days out of {len(cells)} in the period. "
            f"Peak day: {max_val:.0f}."
        ),
    }


def _weekday_heatmap(
    by_date: dict[date, float],
    months: int,
) -> dict[str, Any]:
    """Generate aggregated spending by day of week."""
    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_totals = {i: 0.0 for i in range(7)}
    day_counts = {i: 0 for i in range(7)}

    for d, amount in by_date.items():
        dow = d.weekday()
        day_totals[dow] += amount
        day_counts[dow] += 1

    max_val = max(day_totals.values()) if day_totals else 0

    cells = [
        {
            "day_of_week": i,
            "day_name": DAYS[i],
            "total": round(day_totals[i], 2),
            "average": round(day_totals[i] / day_counts[i], 2) if day_counts[i] > 0 else 0,
            "occurrence_count": day_counts[i],
            "intensity": _intensity(day_totals[i], max_val),
        }
        for i in range(7)
    ]

    busiest = max(cells, key=lambda x: x["total"])

    return {
        "view": "weekday",
        "cells": cells,
        "max_value": round(max_val, 2),
        "busiest_day": busiest["day_name"],
        "months_analyzed": months,
        "summary": f"Highest spending day: {busiest['day_name']} (total: {busiest['total']:.0f}).",
    }


def _monthly_heatmap(
    by_date: dict[date, float],
    months: int,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Generate monthly aggregated heatmap."""
    monthly_totals: dict[str, float] = {}

    for d, amount in by_date.items():
        key = d.strftime("%Y-%m")
        monthly_totals[key] = monthly_totals.get(key, 0.0) + amount

    max_val = max(monthly_totals.values()) if monthly_totals else 0

    # Fill all months in range
    current = start_date.replace(day=1)
    cells = []
    while current <= end_date:
        key = current.strftime("%Y-%m")
        amount = monthly_totals.get(key, 0.0)
        cells.append({
            "month": key,
            "year": current.year,
            "month_num": current.month,
            "amount": round(amount, 2),
            "intensity": _intensity(amount, max_val),
        })
        # Advance to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return {
        "view": "monthly",
        "cells": cells,
        "max_value": round(max_val, 2),
        "total_spend": round(sum(monthly_totals.values()), 2),
        "months_analyzed": len(monthly_totals),
        "summary": (
            f"Peak month: {max(monthly_totals, key=monthly_totals.get)} "
            f"with {max_val:.0f} spending."
            if monthly_totals else "No spending data found."
        ),
    }


def _empty_heatmap(view: str, months: int) -> dict[str, Any]:
    """Return empty heatmap when no data exists."""
    return {
        "view": view,
        "cells": [],
        "max_value": 0,
        "total_spend": 0,
        "months_analyzed": months,
        "summary": "No spending data found for this period.",
    }
