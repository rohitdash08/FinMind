"""
Spending trend heatmap visualization data (issue #116).
Returns day-of-week × week-of-month spend matrix for frontend rendering.
"""
import logging
from datetime import date, timedelta
from sqlalchemy import func, extract
from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.heatmap")

DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]


def get_heatmap(user_id: int, year: int, month: int) -> dict:
    """
    Returns spend matrix: rows=week(1-5), cols=day(Mon-Sun).
    Also returns daily totals array and max value for color scaling.
    """
    rows = (
        db.session.query(Expense.spent_at, func.sum(Expense.amount).label("total"))
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at).all()
    )

    daily = {r.spent_at: float(r.total or 0) for r in rows}

    # Build 5×7 matrix
    matrix = [[0.0] * 7 for _ in range(5)]
    daily_list = []

    first = date(year, month, 1)
    last_day = (date(year, month % 12 + 1, 1) - timedelta(days=1)).day if month < 12 else 31

    for day_num in range(1, last_day + 1):
        try:
            d = date(year, month, day_num)
        except ValueError:
            break
        amt = daily.get(d, 0.0)
        dow = d.weekday()          # 0=Mon
        week_idx = min((d.day - 1 + first.weekday()) // 7, 4)
        matrix[week_idx][dow] = round(amt, 2)
        daily_list.append({"date": d.isoformat(), "amount": round(amt, 2), "day": DAYS[dow]})

    all_vals = [v for row in matrix for v in row]
    max_val = max(all_vals) if all_vals else 0

    return {
        "period": f"{year}-{month:02d}",
        "matrix": matrix,
        "days": DAYS,
        "weeks": [f"Week {i+1}" for i in range(5)],
        "daily": daily_list,
        "max_value": round(max_val, 2),
        "total": round(sum(all_vals), 2),
    }
