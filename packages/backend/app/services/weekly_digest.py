"""Weekly financial summary digest service.

Generates a comprehensive weekly digest highlighting spending trends,
category insights, bill reminders, and actionable recommendations.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import Bill, Category, Expense
from .cache import cache_get, cache_set

logger = logging.getLogger("finmind.weekly_digest")

DIGEST_CACHE_TTL = 3600  # 1 hour


def weekly_digest_cache_key(user_id: int, week_start: str) -> str:
    return f"user:{user_id}:weekly_digest:{week_start}"


def _week_bounds(reference_date: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the week containing reference_date."""
    ref = reference_date or date.today()
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _previous_week_bounds(week_start: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the week before the given week_start."""
    prev_monday = week_start - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def _week_totals(
    uid: int, start: date, end: date
) -> tuple[float, float]:
    """Return (income, expenses) for a date range."""
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


def _category_breakdown(
    uid: int, start: date, end: date
) -> list[dict]:
    """Return spending by category for a date range, sorted descending."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
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
    total = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": (
                round((float(r.total or 0) / total) * 100, 2) if total > 0 else 0
            ),
        }
        for r in rows
    ]


def _daily_spending(uid: int, start: date, end: date) -> list[dict]:
    """Return day-by-day spending totals for the date range."""
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
    spent_map = {r.spent_at: float(r.total or 0) for r in rows}
    result = []
    current = start
    while current <= end:
        result.append({
            "date": current.isoformat(),
            "amount": round(spent_map.get(current, 0.0), 2),
        })
        current += timedelta(days=1)
    return result


def _top_transactions(uid: int, start: date, end: date, limit: int = 5) -> list[dict]:
    """Return the largest expense transactions in the date range."""
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
            "description": e.notes or "Transaction",
            "amount": float(e.amount),
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
            "currency": e.currency,
        }
        for e in rows
    ]


def _upcoming_bills(uid: int, start: date, end: date) -> list[dict]:
    """Return bills due within the given date range."""
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date)
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
            "autopay_enabled": b.autopay_enabled,
        }
        for b in bills
    ]


def _compute_trends(
    current_income: float,
    current_expenses: float,
    prev_income: float,
    prev_expenses: float,
) -> dict:
    """Compute week-over-week trend percentages."""
    if prev_expenses > 0:
        expense_change_pct = round(
            ((current_expenses - prev_expenses) / prev_expenses) * 100, 2
        )
    else:
        expense_change_pct = 0.0 if current_expenses == 0 else 100.0

    if prev_income > 0:
        income_change_pct = round(
            ((current_income - prev_income) / prev_income) * 100, 2
        )
    else:
        income_change_pct = 0.0 if current_income == 0 else 100.0

    return {
        "expense_change_pct": expense_change_pct,
        "income_change_pct": income_change_pct,
        "previous_week_expenses": round(prev_expenses, 2),
        "previous_week_income": round(prev_income, 2),
    }


def _generate_insights(
    current_expenses: float,
    prev_expenses: float,
    category_breakdown: list[dict],
    daily_spending: list[dict],
    upcoming_bills: list[dict],
) -> list[str]:
    """Generate actionable text insights based on the week's data."""
    insights = []

    # Spending trend insight
    if prev_expenses > 0:
        change_pct = ((current_expenses - prev_expenses) / prev_expenses) * 100
        if change_pct > 20:
            insights.append(
                f"Spending increased {change_pct:.0f}% compared to last week. "
                "Review your largest expenses to identify areas to cut back."
            )
        elif change_pct < -20:
            insights.append(
                f"Great job! Spending decreased {abs(change_pct):.0f}% compared "
                "to last week. Keep up the momentum."
            )
        else:
            insights.append(
                "Spending is relatively stable compared to last week."
            )
    elif current_expenses > 0:
        insights.append(
            "This is your first tracked week with expenses. "
            "Keep logging to unlock trend insights."
        )

    # Top category insight
    if category_breakdown:
        top = category_breakdown[0]
        if top["share_pct"] > 50:
            insights.append(
                f"{top['category_name']} accounts for {top['share_pct']:.0f}% "
                "of your spending. Consider setting a budget cap for this category."
            )

    # Peak spending day
    if daily_spending:
        peak = max(daily_spending, key=lambda d: d["amount"])
        if peak["amount"] > 0:
            insights.append(
                f"Your highest spending day was {peak['date']} "
                f"at {peak['amount']:.2f}."
            )

    # Upcoming bills warning
    total_bills = sum(b["amount"] for b in upcoming_bills)
    if total_bills > 0:
        insights.append(
            f"You have {len(upcoming_bills)} bill(s) totaling "
            f"{total_bills:.2f} due next week. Plan your cash flow accordingly."
        )

    return insights


def generate_weekly_digest(
    user_id: int,
    week_of: date | None = None,
) -> dict:
    """Generate a comprehensive weekly financial summary.

    Args:
        user_id: The authenticated user's ID.
        week_of: Any date within the desired week. Defaults to current week.

    Returns:
        A dictionary containing the full weekly digest payload.
    """
    week_start, week_end = _week_bounds(week_of)
    cache_key = weekly_digest_cache_key(user_id, week_start.isoformat())
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Current week data
    current_income, current_expenses = _week_totals(user_id, week_start, week_end)
    categories = _category_breakdown(user_id, week_start, week_end)
    daily = _daily_spending(user_id, week_start, week_end)
    top_txns = _top_transactions(user_id, week_start, week_end)

    # Previous week data for trends
    prev_start, prev_end = _previous_week_bounds(week_start)
    prev_income, prev_expenses = _week_totals(user_id, prev_start, prev_end)

    # Upcoming bills (next week)
    next_week_start = week_end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)
    bills = _upcoming_bills(user_id, next_week_start, next_week_end)

    trends = _compute_trends(
        current_income, current_expenses, prev_income, prev_expenses
    )
    insights = _generate_insights(
        current_expenses, prev_expenses, categories, daily, bills
    )

    transaction_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
        )
        .scalar()
    ) or 0

    payload = {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
        },
        "summary": {
            "total_income": round(current_income, 2),
            "total_expenses": round(current_expenses, 2),
            "net_flow": round(current_income - current_expenses, 2),
            "transaction_count": transaction_count,
        },
        "trends": trends,
        "category_breakdown": categories,
        "daily_spending": daily,
        "top_transactions": top_txns,
        "upcoming_bills": bills,
        "insights": insights,
    }

    cache_set(cache_key, payload, ttl_seconds=DIGEST_CACHE_TTL)
    logger.info(
        "Generated weekly digest user=%s week=%s", user_id, week_start.isoformat()
    )
    return payload
