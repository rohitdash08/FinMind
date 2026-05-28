"""Calendar heatmap service for FinMind.

Generates daily spending data suitable for calendar heatmap visualization.
"""

import logging
from datetime import date, timedelta
from collections import defaultdict
from flask_jwt_extended import get_jwt_identity

from ..extensions import db
from ..models import Expense
from sqlalchemy import func

logger = logging.getLogger("finmind.heatmap")


def get_heatmap_data(user_id: int, year: int, month: int | None = None) -> dict:
    """Generate heatmap data for a user.

    Args:
        user_id: The user ID
        year: Year to generate heatmap for
        month: Optional month (1-12). If None, generates full year.

    Returns:
        Dict with daily totals and metadata for heatmap rendering.
    """
    if month:
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
    else:
        start = date(year, 1, 1)
        end = date(year, 12, 31)

    # Query daily totals
    rows = (
        db.session.query(
            Expense.spent_at,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )

    # Build daily data map
    daily = {}
    for row in rows:
        day_str = row.spent_at.isoformat()
        daily[day_str] = {
            "amount": float(row.total),
            "count": row.count,
        }

    # Fill in missing days with zero
    all_amounts = [d["amount"] for d in daily.values()]
    max_amount = max(all_amounts) if all_amounts else 0
    total = sum(all_amounts)
    active_days = len(all_amounts)

    # Generate complete date range
    days = []
    current = start
    while current <= end:
        day_str = current.isoformat()
        entry = daily.get(day_str, {"amount": 0, "count": 0})
        # Intensity: 0-4 scale (0=no spending, 4=max spending)
        intensity = 0
        if max_amount > 0 and entry["amount"] > 0:
            ratio = entry["amount"] / max_amount
            if ratio <= 0.25:
                intensity = 1
            elif ratio <= 0.50:
                intensity = 2
            elif ratio <= 0.75:
                intensity = 3
            else:
                intensity = 4

        days.append({
            "date": day_str,
            "amount": entry["amount"],
            "count": entry["count"],
            "intensity": intensity,
        })
        current += timedelta(days=1)

    # Streak calculation
    streak = _calculate_streak(daily, start, end)

    return {
        "year": year,
        "month": month,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_spending": round(total, 2),
        "total_transactions": sum(d["count"] for d in daily.values()),
        "active_days": active_days,
        "max_daily": round(max_amount, 2),
        "avg_daily": round(total / max(active_days, 1), 2),
        "current_streak": streak,
        "days": days,
    }


def _calculate_streak(daily: dict, start: date, end: date) -> int:
    """Calculate current spending streak from today backwards."""
    today = date.today()
    streak = 0
    current = today

    while current >= start:
        day_str = current.isoformat()
        if day_str in daily:
            streak += 1
        elif current < today:
            break  # Gap in streak
        current -= timedelta(days=1)

    return streak
