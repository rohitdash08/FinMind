"""Spending trend heatmap visualization data."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Expense
import logging

logger = logging.getLogger("finmind.heatmap")


def generate_heatmap(user_id: int, weeks: int = 12) -> dict:
    """Generate spending heatmap data (day-of-week x week grid).

    Returns a matrix of spending amounts suitable for heatmap visualization,
    similar to GitHub's contribution graph.
    """
    today = date.today()
    start = today - timedelta(weeks=weeks)

    expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.expense_type == "EXPENSE",
        )
        .all()
    )

    # Build daily totals
    daily: dict[str, float] = defaultdict(float)
    for e in expenses:
        if e.spent_at:
            daily[e.spent_at.isoformat()] += float(e.amount)

    # Build heatmap grid (rows=days of week, cols=weeks)
    grid = []
    max_amount = 0.0

    current = start - timedelta(days=start.weekday())  # Start from Monday
    while current <= today:
        day_str = current.isoformat()
        amount = daily.get(day_str, 0.0)
        max_amount = max(max_amount, amount)
        grid.append({
            "date": day_str,
            "weekday": current.weekday(),
            "week": (current - (start - timedelta(days=start.weekday()))).days // 7,
            "amount": round(amount, 2),
        })
        current += timedelta(days=1)

    # Calculate intensity levels (0-4, like GitHub)
    for cell in grid:
        if max_amount > 0:
            cell["level"] = min(4, int(cell["amount"] / max_amount * 4.99))
        else:
            cell["level"] = 0

    # Summary stats
    amounts = [c["amount"] for c in grid if c["amount"] > 0]
    weekday_totals = defaultdict(float)
    for c in grid:
        weekday_totals[c["weekday"]] += c["amount"]

    peak_day = max(weekday_totals, key=weekday_totals.get) if weekday_totals else 0
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    return {
        "grid": grid,
        "weeks": weeks,
        "max_daily_amount": round(max_amount, 2),
        "total_days_with_spending": len(amounts),
        "average_daily": round(sum(amounts) / len(amounts), 2) if amounts else 0,
        "peak_weekday": day_names[peak_day],
        "weekday_totals": {day_names[k]: round(v, 2) for k, v in weekday_totals.items()},
    }
