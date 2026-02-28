"""Weekly financial digest service.

Generates smart weekly summaries with spending trends, category insights,
and actionable observations for a given user and ISO week.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, and_

from ..extensions import db
from ..models import Expense, Category


def _week_bounds(year: int, week: int) -> tuple[date, date]:
    """Return (monday, sunday) for the given ISO year/week."""
    jan4 = date(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _prev_week(year: int, week: int) -> tuple[int, int]:
    """Return (year, week) for the previous ISO week."""
    monday, _ = _week_bounds(year, week)
    prev_monday = monday - timedelta(weeks=1)
    iso = prev_monday.isocalendar()
    return iso[0], iso[1]


def _query_week_totals(
    uid: int, start: date, end: date
) -> tuple[float, float, int]:
    """Return (total_income, total_expenses, transaction_count) for a date range."""
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
    count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0), int(count or 0)


def _query_category_breakdown(
    uid: int, start: date, end: date
) -> list[dict[str, Any]]:
    """Return per-category spending for a date range."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("cat_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("txn_count"),
        )
        .outerjoin(
            Category,
            and_(
                Category.id == Expense.category_id,
                Category.user_id == uid,
            ),
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
    total = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.cat_name,
            "amount": round(float(r.total or 0), 2),
            "transaction_count": int(r.txn_count),
            "share_pct": (
                round((float(r.total or 0) / total) * 100, 1) if total > 0 else 0
            ),
        }
        for r in rows
    ]


def _query_daily_spending(uid: int, start: date, end: date) -> list[dict]:
    """Return daily expense totals for a date range."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    return [
        {"date": r.spent_at.isoformat(), "amount": round(float(r.total or 0), 2)}
        for r in rows
    ]


def _top_transactions(uid: int, start: date, end: date, limit: int = 5) -> list[dict]:
    """Return the largest expense transactions in the period."""
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
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
            "amount": round(float(e.amount), 2),
            "description": e.notes or "",
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
        }
        for e in rows
    ]


def _pct_change(current: float, previous: float) -> float | None:
    """Calculate percentage change; returns None if previous is zero."""
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


def _generate_insights(
    current_expenses: float,
    prev_expenses: float,
    current_cats: list[dict],
    prev_cats: list[dict],
    daily: list[dict],
) -> list[str]:
    """Generate human-readable insights from the weekly data."""
    insights: list[str] = []

    # Overall spending trend
    change = _pct_change(current_expenses, prev_expenses)
    if change is not None:
        direction = "increased" if change > 0 else "decreased"
        insights.append(
            f"Total spending {direction} by {abs(change)}% compared to last week"
            f" (${current_expenses:,.2f} vs ${prev_expenses:,.2f})."
        )
    elif current_expenses > 0:
        insights.append(
            f"You spent ${current_expenses:,.2f} this week"
            " (no data from previous week to compare)."
        )

    # Category comparison insights
    prev_map = {c["category_name"]: c["amount"] for c in prev_cats}
    for cat in current_cats[:5]:
        name = cat["category_name"]
        prev_amt = prev_map.get(name, 0)
        cat_change = _pct_change(cat["amount"], prev_amt)
        if cat_change is not None and abs(cat_change) >= 15:
            direction = "up" if cat_change > 0 else "down"
            insights.append(
                f"{name} spending is {direction} {abs(cat_change)}%"
                f" (${cat['amount']:,.2f} vs ${prev_amt:,.2f} last week)."
            )

    # Highest spending day
    if daily:
        peak = max(daily, key=lambda d: d["amount"])
        insights.append(
            f"Highest spending day: {peak['date']} at ${peak['amount']:,.2f}."
        )

    # Top category dominance
    if current_cats and current_cats[0]["share_pct"] >= 40:
        top = current_cats[0]
        insights.append(
            f"{top['category_name']} dominates at {top['share_pct']}%"
            " of total spending — consider reviewing this category."
        )

    return insights


def generate_weekly_digest(
    uid: int,
    year: int | None = None,
    week: int | None = None,
) -> dict[str, Any]:
    """Generate a complete weekly financial digest for a user.

    Args:
        uid: User ID.
        year: ISO year (defaults to current week).
        week: ISO week number (defaults to current week).

    Returns:
        Dictionary containing the weekly summary, trends, and insights.
    """
    today = date.today()
    if year is None or week is None:
        iso = today.isocalendar()
        year, week = iso[0], iso[1]

    start, end = _week_bounds(year, week)
    prev_year, prev_week = _prev_week(year, week)
    prev_start, prev_end = _week_bounds(prev_year, prev_week)

    # Current week data
    income, expenses, txn_count = _query_week_totals(uid, start, end)
    categories = _query_category_breakdown(uid, start, end)
    daily = _query_daily_spending(uid, start, end)
    top_txns = _top_transactions(uid, start, end)

    # Previous week data for comparison
    prev_income, prev_expenses, prev_txn_count = _query_week_totals(
        uid, prev_start, prev_end
    )
    prev_categories = _query_category_breakdown(uid, prev_start, prev_end)

    # Compute trends
    expense_change = _pct_change(expenses, prev_expenses)
    income_change = _pct_change(income, prev_income)

    # Generate insights
    insights = _generate_insights(
        expenses, prev_expenses, categories, prev_categories, daily
    )

    return {
        "period": {
            "year": year,
            "week": week,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
            "transaction_count": txn_count,
        },
        "trends": {
            "expense_change_pct": expense_change,
            "income_change_pct": income_change,
            "prev_week_expenses": round(prev_expenses, 2),
            "prev_week_income": round(prev_income, 2),
        },
        "category_breakdown": categories,
        "daily_spending": daily,
        "top_transactions": top_txns,
        "insights": insights,
    }
