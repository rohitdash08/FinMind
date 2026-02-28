"""Weekly financial digest service.

Aggregates expenses, bills, and category trends for a given ISO week,
producing a structured summary with highlights and insights.
"""

from datetime import date, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import Bill, Category, Expense


def _week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Return (monday, sunday) for the given ISO year/week."""
    jan4 = date(iso_year, 1, 4)
    start = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start + timedelta(weeks=iso_week - 1)
    return monday, monday + timedelta(days=6)


def _prev_week(iso_year: int, iso_week: int) -> tuple[int, int]:
    """Return (year, week) for the previous ISO week."""
    monday, _ = _week_bounds(iso_year, iso_week)
    prev_monday = monday - timedelta(weeks=1)
    return prev_monday.isocalendar()[:2]


def _week_expenses(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .all()
    )
    return [
        {
            "id": r.id,
            "amount": float(r.amount),
            "currency": r.currency,
            "type": r.expense_type,
            "notes": r.notes,
            "category_id": r.category_id,
            "date": r.spent_at.isoformat(),
        }
        for r in rows
    ]


def _category_totals(uid: int, start: date, end: date) -> dict[str, float]:
    rows = (
        db.session.query(
            Category.name,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .outerjoin(Expense, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Category.name)
        .all()
    )
    return {name: float(total) for name, total in rows}


def _total_by_type(expenses: list[dict]) -> tuple[float, float]:
    income = sum(e["amount"] for e in expenses if e["type"] == "INCOME")
    spending = sum(e["amount"] for e in expenses if e["type"] != "INCOME")
    return round(income, 2), round(spending, 2)


def _upcoming_bills(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active == True,  # noqa: E712
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .all()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "amount": float(r.amount),
            "due_date": r.next_due_date.isoformat(),
            "autopay": r.autopay_enabled,
        }
        for r in rows
    ]


def weekly_digest(uid: int, iso_year: int | None = None, iso_week: int | None = None) -> dict:
    """Generate a weekly financial digest for the given user and week."""
    today = date.today()
    if iso_year is None or iso_week is None:
        iso_year, iso_week, _ = today.isocalendar()

    start, end = _week_bounds(iso_year, iso_week)

    expenses = _week_expenses(uid, start, end)
    income, spending = _total_by_type(expenses)
    categories = _category_totals(uid, start, end)
    bills = _upcoming_bills(uid, start, end)

    prev_year, prev_week = _prev_week(iso_year, iso_week)
    prev_start, prev_end = _week_bounds(prev_year, prev_week)
    prev_expenses = _week_expenses(uid, prev_start, prev_end)
    _, prev_spending = _total_by_type(prev_expenses)

    if prev_spending > 0:
        wow_change = round(((spending - prev_spending) / prev_spending) * 100, 2)
    else:
        wow_change = 0.0

    top_category = max(categories, key=categories.get) if categories else None

    highlights = []
    if wow_change > 10:
        highlights.append(f"Spending increased {wow_change}% vs last week.")
    elif wow_change < -10:
        highlights.append(f"Spending decreased {abs(wow_change)}% vs last week.")
    else:
        highlights.append("Spending is stable compared to last week.")

    if top_category:
        highlights.append(
            f"Top spending category: {top_category} "
            f"(${categories[top_category]:.2f})."
        )

    non_autopay_bills = [b for b in bills if not b["autopay"]]
    if non_autopay_bills:
        total_due = sum(b["amount"] for b in non_autopay_bills)
        highlights.append(
            f"{len(non_autopay_bills)} bill(s) due this week totaling ${total_due:.2f}."
        )

    return {
        "week": f"{iso_year}-W{iso_week:02d}",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "summary": {
            "total_income": income,
            "total_spending": spending,
            "net_flow": round(income - spending, 2),
            "transaction_count": len(expenses),
        },
        "comparison": {
            "previous_week": f"{prev_year}-W{prev_week:02d}",
            "previous_spending": prev_spending,
            "week_over_week_change_pct": wow_change,
        },
        "categories": categories,
        "top_category": top_category,
        "bills_due": bills,
        "highlights": highlights,
    }
