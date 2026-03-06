from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Category, Bill


def weekly_summary(user_id: int, week_start: date, week_end: date) -> dict:
    """Generate a weekly financial digest for the given user and date range."""

    income = _sum_by_type(user_id, week_start, week_end, "INCOME")
    expenses = _sum_by_type(user_id, week_start, week_end, "EXPENSE")

    prev_start = week_start - timedelta(days=7)
    prev_end = week_start - timedelta(days=1)
    prev_income = _sum_by_type(user_id, prev_start, prev_end, "INCOME")
    prev_expenses = _sum_by_type(user_id, prev_start, prev_end, "EXPENSE")

    category_breakdown = _category_breakdown(user_id, week_start, week_end)

    top_expenses = _top_expenses(user_id, week_start, week_end, limit=5)

    upcoming_bills = _upcoming_bills(user_id, week_start, week_end)

    daily_spending = _daily_spending(user_id, week_start, week_end)

    insights = _generate_insights(
        income, expenses, prev_income, prev_expenses, category_breakdown
    )

    return {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
        },
        "summary": {
            "total_income": income,
            "total_expenses": expenses,
            "net_flow": round(income - expenses, 2),
            "prev_week_income": prev_income,
            "prev_week_expenses": prev_expenses,
            "income_change_pct": _pct_change(prev_income, income),
            "expense_change_pct": _pct_change(prev_expenses, expenses),
        },
        "category_breakdown": category_breakdown,
        "top_expenses": top_expenses,
        "daily_spending": daily_spending,
        "upcoming_bills": upcoming_bills,
        "insights": insights,
    }


def _sum_by_type(
    user_id: int, start: date, end: date, expense_type: str
) -> float:
    if expense_type == "EXPENSE":
        filt = Expense.expense_type != "INCOME"
    else:
        filt = Expense.expense_type == "INCOME"

    result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            filt,
        )
        .scalar()
    )
    return round(float(result or 0), 2)


def _category_breakdown(user_id: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == user_id),
        )
        .filter(
            Expense.user_id == user_id,
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
            "share_pct": (
                round((float(r.total_amount or 0) / total) * 100, 2)
                if total > 0
                else 0
            ),
        }
        for r in rows
    ]


def _top_expenses(
    user_id: int, start: date, end: date, limit: int = 5
) -> list[dict]:
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "amount": float(e.amount),
            "notes": e.notes or "Transaction",
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
        }
        for e in rows
    ]


def _daily_spending(user_id: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at.asc())
        .all()
    )
    return [
        {"date": r.spent_at.isoformat(), "amount": float(r.total or 0)}
        for r in rows
    ]


def _upcoming_bills(user_id: int, start: date, end: date) -> list[dict]:
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
        }
        for b in bills
    ]


def _pct_change(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return round(((new - old) / old) * 100, 2)


def _generate_insights(
    income: float,
    expenses: float,
    prev_income: float,
    prev_expenses: float,
    categories: list[dict],
) -> list[str]:
    insights = []

    if expenses > income and income > 0:
        insights.append(
            f"You spent {round(((expenses - income) / income) * 100, 1)}% more than you earned this week."
        )
    elif income > expenses and expenses > 0:
        savings_rate = round(((income - expenses) / income) * 100, 1)
        insights.append(f"Great job! You saved {savings_rate}% of your income this week.")

    if prev_expenses > 0 and expenses > prev_expenses:
        pct = round(((expenses - prev_expenses) / prev_expenses) * 100, 1)
        insights.append(f"Your spending increased by {pct}% compared to last week.")
    elif prev_expenses > 0 and expenses < prev_expenses:
        pct = round(((prev_expenses - expenses) / prev_expenses) * 100, 1)
        insights.append(f"Your spending decreased by {pct}% compared to last week.")

    if categories:
        top = categories[0]
        insights.append(
            f"Top spending category: {top['category_name']} "
            f"({top['share_pct']}% of total expenses)."
        )

    if not insights:
        insights.append("No financial activity recorded this week.")

    return insights
