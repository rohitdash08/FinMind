from datetime import date, timedelta
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Bill, Category
import logging

logger = logging.getLogger("finmind.digest")


def generate_weekly_digest(uid: int, week_start: date | None = None) -> dict:
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)

    income, expenses = _weekly_totals(uid, week_start, week_end)
    category_breakdown = _weekly_category_breakdown(uid, week_start, week_end)
    upcoming_bills = _upcoming_bills(uid, week_end)
    spending_trend = _spending_trend(uid, week_start)
    top_merchants = _top_expense_descriptions(uid, week_start, week_end)
    savings_rate = _savings_rate(income, expenses)
    insights = _generate_insights(income, expenses, category_breakdown, spending_trend, savings_rate)

    digest = {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
        },
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
            "savings_rate_pct": savings_rate,
            "transaction_count": _weekly_transaction_count(uid, week_start, week_end),
        },
        "category_breakdown": category_breakdown,
        "spending_trend": spending_trend,
        "top_merchants": top_merchants,
        "upcoming_bills": upcoming_bills,
        "insights": insights,
    }
    return digest


def _weekly_totals(uid: int, start: date, end: date) -> tuple[float, float]:
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _weekly_category_breakdown(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    total = sum(float(r.total_amount or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": float(r.total_amount or 0),
            "share_pct": round((float(r.total_amount or 0) / total) * 100, 2) if total > 0 else 0,
        }
        for r in rows
    ]


def _weekly_transaction_count(uid: int, start: date, end: date) -> int:
    count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return int(count or 0)


def _upcoming_bills(uid: int, from_date: date) -> list[dict]:
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= from_date,
        )
        .order_by(Bill.next_due_date.asc())
        .limit(5)
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
        }
        for b in bills
    ]


def _spending_trend(uid: int, current_week_start: date) -> dict:
    prev_week_start = current_week_start - timedelta(weeks=1)
    prev_week_end = current_week_start - timedelta(days=1)

    _, current_expenses = _weekly_totals(uid, current_week_start, current_week_start + timedelta(days=6))
    _, prev_expenses = _weekly_totals(uid, prev_week_start, prev_week_end)

    change_pct = 0.0
    if prev_expenses > 0:
        change_pct = round(((current_expenses - prev_expenses) / prev_expenses) * 100, 2)

    return {
        "current_week_expenses": round(current_expenses, 2),
        "previous_week_expenses": round(prev_expenses, 2),
        "week_over_week_change_pct": change_pct,
        "direction": "up" if change_pct > 0 else ("down" if change_pct < 0 else "flat"),
    }


def _top_expense_descriptions(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.notes,
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.notes)
        .order_by(func.sum(Expense.amount).desc())
        .limit(5)
        .all()
    )
    return [
        {
            "name": r.notes or "Unnamed",
            "total_amount": float(r.total_amount or 0),
            "count": int(r.count or 0),
        }
        for r in rows
    ]


def _savings_rate(income: float, expenses: float) -> float:
    if income <= 0:
        return 0.0
    rate = ((income - expenses) / income) * 100
    return round(max(rate, 0.0), 2)


def _generate_insights(
    income: float,
    expenses: float,
    categories: list[dict],
    trend: dict,
    savings_rate: float,
) -> list[str]:
    insights: list[str] = []

    if savings_rate >= 20:
        insights.append("Great savings rate this week! You're saving over 20% of income.")
    elif savings_rate >= 10:
        insights.append("Decent savings rate. Aim for 20%+ if possible.")
    elif savings_rate > 0:
        insights.append("Savings rate is below 10%. Look for areas to cut back.")
    else:
        insights.append("You spent more than you earned this week. Review discretionary spending.")

    if trend["direction"] == "up" and trend["week_over_week_change_pct"] > 20:
        insights.append(f"Spending is up {abs(trend['week_over_week_change_pct'])}% compared to last week.")
    elif trend["direction"] == "down" and trend["week_over_week_change_pct"] < -10:
        insights.append(f"Spending is down {abs(trend['week_over_week_change_pct'])}% compared to last week. Nice work!")

    if categories:
        top = categories[0]
        if top["share_pct"] > 40:
            insights.append(f"{top['category_name']} accounts for {top['share_pct']}% of spending. Consider diversifying.")

    if income > 0 and expenses > income * 0.9:
        insights.append("Expenses consumed over 90% of income. Consider automating savings.")

    return insights
