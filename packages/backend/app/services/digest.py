"""Weekly financial digest service.

Generates structured weekly summaries from transaction data, highlighting
spending trends, category insights, and actionable observations.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense
from ..services.cache import cache_get, cache_set


def weekly_digest_key(user_id: int, week_start: str) -> str:
    """Cache key for a user's weekly digest."""
    return f"user:{user_id}:weekly_digest:{week_start}"


def _week_bounds(ref: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the week containing *ref* (default: last full week)."""
    today = ref or date.today()
    # Last completed week: previous Monday through previous Sunday
    days_since_monday = today.weekday()  # Monday=0
    last_monday = today - timedelta(days=days_since_monday + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def _week_bounds_for(week_start_iso: str) -> tuple[date, date]:
    """Parse an ISO date string and return its Mon–Sun range."""
    start = date.fromisoformat(week_start_iso)
    # Snap to Monday
    start = start - timedelta(days=start.weekday())
    return start, start + timedelta(days=6)


def _prior_week(week_start: date) -> tuple[date, date]:
    """Return bounds for the week before *week_start*."""
    prior_monday = week_start - timedelta(days=7)
    return prior_monday, prior_monday + timedelta(days=6)


def _query_totals(
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
) -> list[dict[str, Any]]:
    """Return per-category spend for the date range."""
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
    total_spend = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": (
                round((float(r.total or 0) / total_spend) * 100, 2)
                if total_spend > 0
                else 0
            ),
        }
        for r in rows
    ]


def _daily_spending(uid: int, start: date, end: date) -> list[dict[str, Any]]:
    """Return daily expense totals across the date range."""
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
        .order_by(Expense.spent_at.asc())
        .all()
    )
    # Fill in zero-spend days
    result = []
    current = start
    row_map = {r.spent_at: float(r.total or 0) for r in rows}
    while current <= end:
        result.append({
            "date": current.isoformat(),
            "amount": round(row_map.get(current, 0.0), 2),
        })
        current += timedelta(days=1)
    return result


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
            "amount": float(e.amount),
            "description": e.notes or "",
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
        }
        for e in rows
    ]


def _generate_insights(
    current_income: float,
    current_expenses: float,
    prev_income: float,
    prev_expenses: float,
    categories: list[dict],
    daily: list[dict],
) -> list[str]:
    """Generate human-readable insight strings from the digest data."""
    insights: list[str] = []

    # Week-over-week spending change
    if prev_expenses > 0:
        pct = ((current_expenses - prev_expenses) / prev_expenses) * 100
        direction = "up" if pct > 0 else "down"
        insights.append(
            f"Spending is {direction} {abs(pct):.1f}% compared to the previous week."
        )
    elif current_expenses > 0:
        insights.append("This is your first week with recorded expenses.")

    # Net flow
    net = current_income - current_expenses
    if net > 0:
        insights.append(
            f"You saved {net:,.2f} this week (income exceeded expenses)."
        )
    elif net < 0:
        insights.append(
            f"You spent {abs(net):,.2f} more than you earned this week."
        )

    # Top category
    if categories:
        top = categories[0]
        insights.append(
            f"Your biggest spending category was {top['category_name']} "
            f"at {top['amount']:,.2f} ({top['share_pct']:.0f}% of total)."
        )

    # Peak spending day
    if daily:
        peak = max(daily, key=lambda d: d["amount"])
        if peak["amount"] > 0:
            day_name = date.fromisoformat(peak["date"]).strftime("%A")
            insights.append(
                f"Peak spending day was {day_name} ({peak['date']}) "
                f"at {peak['amount']:,.2f}."
            )

    # Low-activity flag
    active_days = sum(1 for d in daily if d["amount"] > 0)
    if active_days <= 2 and current_expenses > 0:
        insights.append(
            "Spending was concentrated in just a few days this week."
        )

    return insights


def generate_weekly_digest(
    uid: int,
    week_start: str | None = None,
    *,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Build the full weekly digest payload for a user.

    Parameters
    ----------
    uid : int
        The authenticated user's ID.
    week_start : str | None
        ISO date of the Monday to report on.  Defaults to last completed week.
    use_cache : bool
        When True, serve from Redis if available and cache the result.
    """
    if week_start:
        start, end = _week_bounds_for(week_start)
    else:
        start, end = _week_bounds()

    cache_key = weekly_digest_key(uid, start.isoformat())

    if use_cache:
        cached = cache_get(cache_key)
        if cached:
            return cached

    # Current week data
    income, expenses = _query_totals(uid, start, end)
    categories = _category_breakdown(uid, start, end)
    daily = _daily_spending(uid, start, end)
    top_txns = _top_transactions(uid, start, end)

    # Previous week data for comparison
    prev_start, prev_end = _prior_week(start)
    prev_income, prev_expenses = _query_totals(uid, prev_start, prev_end)

    # Week-over-week change
    if prev_expenses > 0:
        wow_change_pct = round(
            ((expenses - prev_expenses) / prev_expenses) * 100, 2
        )
    else:
        wow_change_pct = 0.0

    insights = _generate_insights(
        income, expenses, prev_income, prev_expenses, categories, daily
    )

    payload: dict[str, Any] = {
        "period": {
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
        },
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
            "transaction_count": (
                db.session.query(func.count(Expense.id))
                .filter(
                    Expense.user_id == uid,
                    Expense.spent_at >= start,
                    Expense.spent_at <= end,
                )
                .scalar()
                or 0
            ),
        },
        "comparison": {
            "prev_week_expenses": round(prev_expenses, 2),
            "prev_week_income": round(prev_income, 2),
            "week_over_week_change_pct": wow_change_pct,
        },
        "category_breakdown": categories,
        "daily_spending": daily,
        "top_transactions": top_txns,
        "insights": insights,
    }

    if use_cache:
        # Cache for 1 hour — digest data is historical so doesn't change often
        cache_set(cache_key, payload, ttl_seconds=3600)

    return payload


def list_available_digests(uid: int, count: int = 12) -> list[dict[str, str]]:
    """Return a list of weeks that have expense data, most recent first.

    Useful for the frontend to show a week-picker for past digests.
    """
    today = date.today()
    digests: list[dict[str, str]] = []

    # Walk backwards through weeks
    current_monday = today - timedelta(days=today.weekday() + 7)
    for _ in range(count):
        sunday = current_monday + timedelta(days=6)
        has_data = (
            db.session.query(Expense.id)
            .filter(
                Expense.user_id == uid,
                Expense.spent_at >= current_monday,
                Expense.spent_at <= sunday,
            )
            .first()
        )
        if has_data:
            digests.append({
                "week_start": current_monday.isoformat(),
                "week_end": sunday.isoformat(),
            })
        current_monday -= timedelta(days=7)

    return digests
