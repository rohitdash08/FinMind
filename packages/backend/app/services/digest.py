"""Weekly financial digest service.

Generates weekly summaries highlighting spending trends and insights.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, extract

from ..extensions import db
from ..models import Expense, Category


def _week_range(target_date: date | None = None) -> tuple[date, date]:
    """Return (start, end) of the ISO week containing *target_date*."""
    d = target_date or date.today()
    start = d - timedelta(days=d.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start, end


def _previous_week_range(target_date: date | None = None) -> tuple[date, date]:
    """Return (start, end) of the week before the one containing *target_date*."""
    d = target_date or date.today()
    start = d - timedelta(days=d.weekday() + 7)
    end = start + timedelta(days=6)
    return start, end


def _query_totals(uid: int, start: date, end: date) -> dict:
    """Query income and expense totals for a date range."""
    rows = (
        db.session.query(
            Expense.expense_type,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.expense_type)
        .all()
    )
    totals = {"INCOME": Decimal("0"), "EXPENSE": Decimal("0")}
    for expense_type, amount in rows:
        totals[expense_type] = Decimal(str(amount))
    return totals


def _query_category_breakdown(uid: int, start: date, end: date) -> list[dict]:
    """Return per-category expense breakdown sorted by amount descending."""
    rows = (
        db.session.query(
            Category.name,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "EXPENSE",
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    return [
        {
            "category": name or "Uncategorized",
            "total": float(total),
            "count": count,
        }
        for name, total, count in rows
    ]


def _query_daily_spending(uid: int, start: date, end: date) -> list[dict]:
    """Return daily spending totals for the date range."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.sum(Expense.amount),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "EXPENSE",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    return [
        {"date": str(d), "amount": float(amount)}
        for d, amount in rows
    ]


def weekly_digest(uid: int, target_date: date | None = None) -> dict:
    """Generate a weekly financial digest for the given user.

    Returns a dict containing:
    - period: start/end dates
    - totals: income, expenses, net
    - category_breakdown: per-category spending
    - daily_spending: day-by-day expenses
    - comparison: vs previous week (amount change & percentage)
    - highlights: notable observations
    """
    start, end = _week_range(target_date)
    prev_start, prev_end = _previous_week_range(target_date)

    totals = _query_totals(uid, start, end)
    prev_totals = _query_totals(uid, prev_start, prev_end)

    income = float(totals["INCOME"])
    expenses = float(totals["EXPENSE"])
    net = income - expenses

    prev_expenses = float(prev_totals["EXPENSE"])
    expense_change = expenses - prev_expenses
    expense_change_pct = (
        round((expense_change / prev_expenses) * 100, 1) if prev_expenses else None
    )

    categories = _query_category_breakdown(uid, start, end)
    daily = _query_daily_spending(uid, start, end)

    # Generate highlights
    highlights = []
    if expense_change_pct is not None:
        if expense_change_pct > 20:
            highlights.append(
                f"⚠️ Spending increased by {expense_change_pct}% compared to last week."
            )
        elif expense_change_pct < -20:
            highlights.append(
                f"🎉 Spending decreased by {abs(expense_change_pct)}% compared to last week!"
            )
        else:
            highlights.append(
                f"📊 Spending is roughly stable vs last week ({expense_change_pct:+.1f}%)."
            )

    if categories:
        top = categories[0]
        highlights.append(
            f"💰 Top spending category: {top['category']} ({top['total']:.2f})"
        )

    if net < 0:
        highlights.append("🔴 You spent more than you earned this week.")
    elif income > 0:
        savings_rate = round((net / income) * 100, 1)
        highlights.append(f"💚 Savings rate: {savings_rate}%")

    return {
        "period": {
            "start": str(start),
            "end": str(end),
        },
        "totals": {
            "income": income,
            "expenses": expenses,
            "net": net,
        },
        "comparison": {
            "previous_week_expenses": prev_expenses,
            "change": expense_change,
            "change_percent": expense_change_pct,
        },
        "category_breakdown": categories,
        "daily_spending": daily,
        "highlights": highlights,
    }
