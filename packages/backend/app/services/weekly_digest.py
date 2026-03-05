from datetime import date, datetime, timedelta

from sqlalchemy import and_, func

from ..extensions import db
from ..models import Expense


def _date_range_for_week(week: str) -> tuple[date, date]:
    year, week_no = map(int, week.split("-W"))
    start = date.fromisocalendar(year, week_no, 1)
    end = start + timedelta(days=6)
    return start, end


def _sum_by_type(uid: int, start: date, end: date, expense_type: str) -> float:
    total = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == expense_type,
            Expense.spent_at >= datetime.combine(start, datetime.min.time()),
            Expense.spent_at < datetime.combine(end + timedelta(days=1), datetime.min.time()),
        )
        .scalar()
    )
    return float(total or 0)


def _top_categories(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= datetime.combine(start, datetime.min.time()),
            Expense.spent_at < datetime.combine(end + timedelta(days=1), datetime.min.time()),
        )
        .group_by(Expense.category_id)
        .order_by(func.coalesce(func.sum(Expense.amount), 0).desc())
        .limit(3)
        .all()
    )
    return [
        {
            "category_id": str(category_id or "uncat"),
            "amount": round(float(total), 2),
        }
        for category_id, total in rows
    ]


def _trend_summary(current_expense: float, previous_expense: float) -> dict:
    if previous_expense > 0:
        pct = round(((current_expense - previous_expense) / previous_expense) * 100, 2)
    else:
        pct = 0.0

    if current_expense > previous_expense:
        trend = "up"
    elif current_expense < previous_expense:
        trend = "down"
    else:
        trend = "flat"

    return {"trend": trend, "change_pct": pct}


def build_weekly_digest(uid: int, week: str) -> dict:
    start, end = _date_range_for_week(week)
    prev_start = start - timedelta(days=7)
    prev_end = end - timedelta(days=7)

    income = _sum_by_type(uid, start, end, "INCOME")
    expense = _sum_by_type(uid, start, end, "EXPENSE")
    previous_expense = _sum_by_type(uid, prev_start, prev_end, "EXPENSE")

    top_categories = _top_categories(uid, start, end)
    trend = _trend_summary(expense, previous_expense)

    insights: list[str] = []
    if trend["trend"] == "up":
        insights.append("Spending increased vs last week. Review top categories.")
    elif trend["trend"] == "down":
        insights.append("Great progress: spending decreased vs last week.")
    else:
        insights.append("Spending stayed stable compared with last week.")

    if income > 0 and expense > income:
        insights.append("Expenses exceeded income this week.")

    return {
        "week": week,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "totals": {
            "income": round(income, 2),
            "expense": round(expense, 2),
            "net": round(income - expense, 2),
        },
        "comparison": {
            "previous_week_expense": round(previous_expense, 2),
            "trend": trend,
        },
        "top_categories": top_categories,
        "insights": insights,
    }
