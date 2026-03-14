"""Weekly financial digest generation service.

Computes comprehensive weekly summaries including spending trends,
category breakdowns, savings rate, and rolling analysis.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, and_

from ..extensions import db
from ..models import Expense, Category, WeeklyDigest


def _week_bounds(ref: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the week containing *ref* (default today)."""
    d = ref or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _prev_week_bounds(week_start: date) -> tuple[date, date]:
    prev_monday = week_start - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def _query_totals(user_id: int, start: date, end: date) -> dict[str, float]:
    """Return income and expense totals for a date range."""
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return {
        "income": float(income or 0),
        "expenses": float(expenses or 0),
    }


def _category_breakdown(user_id: int, start: date, end: date) -> list[dict[str, Any]]:
    """Category-level expense breakdown for a date range."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .outerjoin(
            Category,
            and_(Category.id == Expense.category_id, Category.user_id == user_id),
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
    total = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": round((float(r.total or 0) / total) * 100, 2) if total > 0 else 0,
        }
        for r in rows
    ]


def _biggest_expense(user_id: int, start: date, end: date) -> dict[str, Any] | None:
    """Find the single largest expense in the period."""
    row = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .first()
    )
    if not row:
        return None
    return {
        "id": row.id,
        "amount": float(row.amount),
        "description": row.notes or "Transaction",
        "date": row.spent_at.isoformat(),
        "category_id": row.category_id,
    }


def _pct_change(current: float, previous: float) -> float | None:
    """Calculate percentage change; returns None if previous is zero."""
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 2)


def _rolling_trend(user_id: int, current_week_start: date, num_weeks: int = 3) -> list[dict]:
    """Return spending totals for the last *num_weeks* weeks (including current)."""
    weeks = []
    for i in range(num_weeks):
        ws = current_week_start - timedelta(weeks=i)
        we = ws + timedelta(days=6)
        totals = _query_totals(user_id, ws, we)
        weeks.append({
            "week_start": ws.isoformat(),
            "week_end": we.isoformat(),
            "income": totals["income"],
            "expenses": totals["expenses"],
            "net": round(totals["income"] - totals["expenses"], 2),
        })
    weeks.reverse()  # oldest first
    return weeks


def _daily_breakdown(user_id: int, start: date, end: date) -> list[dict]:
    """Per-day spending totals for chart visualization."""
    days = []
    current = start
    while current <= end:
        day_total = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at == current,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        day_income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at == current,
                Expense.expense_type == "INCOME",
            )
            .scalar()
        )
        days.append({
            "date": current.isoformat(),
            "day_name": current.strftime("%A"),
            "expenses": float(day_total or 0),
            "income": float(day_income or 0),
        })
        current += timedelta(days=1)
    return days


def generate_weekly_digest(user_id: int, ref_date: date | None = None) -> dict[str, Any]:
    """Build a comprehensive weekly financial digest.

    Parameters
    ----------
    user_id : int
        The authenticated user.
    ref_date : date, optional
        Any date within the target week. Defaults to today.

    Returns
    -------
    dict
        Full digest payload suitable for JSON serialization.
    """
    week_start, week_end = _week_bounds(ref_date)
    prev_start, prev_end = _prev_week_bounds(week_start)

    # Core totals
    current = _query_totals(user_id, week_start, week_end)
    previous = _query_totals(user_id, prev_start, prev_end)

    spending_change = _pct_change(current["expenses"], previous["expenses"])
    income_change = _pct_change(current["income"], previous["income"])

    # Savings rate
    savings_rate = None
    if current["income"] > 0:
        savings_rate = round(
            ((current["income"] - current["expenses"]) / current["income"]) * 100, 2
        )

    # Category breakdown
    categories = _category_breakdown(user_id, week_start, week_end)

    # Biggest expense
    biggest = _biggest_expense(user_id, week_start, week_end)

    # Rolling trend (3-week)
    trend = _rolling_trend(user_id, week_start, num_weeks=3)

    # Daily breakdown
    daily = _daily_breakdown(user_id, week_start, week_end)

    # Transaction count
    tx_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
        )
        .scalar()
    ) or 0

    # Average daily spending
    days_elapsed = max(1, (min(date.today(), week_end) - week_start).days + 1)
    avg_daily_spending = round(current["expenses"] / days_elapsed, 2)

    # Build insights list
    insights = _generate_insights(
        current, previous, spending_change, income_change,
        savings_rate, categories, biggest, trend
    )

    summary = {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
        },
        "overview": {
            "total_income": current["income"],
            "total_expenses": current["expenses"],
            "net_flow": round(current["income"] - current["expenses"], 2),
            "savings_rate": savings_rate,
            "transaction_count": tx_count,
            "avg_daily_spending": avg_daily_spending,
        },
        "comparison": {
            "prev_week_income": previous["income"],
            "prev_week_expenses": previous["expenses"],
            "spending_change_pct": spending_change,
            "income_change_pct": income_change,
        },
        "category_breakdown": categories,
        "biggest_expense": biggest,
        "daily_breakdown": daily,
        "trend": trend,
        "insights": insights,
    }

    return summary


def _generate_insights(
    current: dict, previous: dict,
    spending_change: float | None, income_change: float | None,
    savings_rate: float | None, categories: list,
    biggest: dict | None, trend: list,
) -> list[dict[str, str]]:
    """Generate human-readable insight bullets."""
    insights: list[dict[str, str]] = []

    # Spending trend
    if spending_change is not None:
        if spending_change > 10:
            insights.append({
                "type": "warning",
                "title": "Spending Increase",
                "message": f"Your spending increased by {spending_change:.1f}% compared to last week.",
            })
        elif spending_change < -10:
            insights.append({
                "type": "success",
                "title": "Spending Decrease",
                "message": f"Great job! Spending decreased by {abs(spending_change):.1f}% from last week.",
            })
        else:
            insights.append({
                "type": "info",
                "title": "Spending Stable",
                "message": f"Your spending changed by {spending_change:+.1f}% compared to last week.",
            })
    elif current["expenses"] > 0:
        insights.append({
            "type": "info",
            "title": "First Week Tracked",
            "message": "No previous week data for comparison. Keep tracking for trend analysis!",
        })

    # Savings rate
    if savings_rate is not None:
        if savings_rate >= 20:
            insights.append({
                "type": "success",
                "title": "Strong Savings",
                "message": f"You saved {savings_rate:.1f}% of your income this week. Excellent!",
            })
        elif savings_rate >= 0:
            insights.append({
                "type": "info",
                "title": "Savings Rate",
                "message": f"You saved {savings_rate:.1f}% of your income. Aim for 20%+.",
            })
        else:
            insights.append({
                "type": "warning",
                "title": "Overspending",
                "message": f"You spent {abs(savings_rate):.1f}% more than you earned this week.",
            })

    # Top category
    if categories:
        top = categories[0]
        insights.append({
            "type": "info",
            "title": "Top Spending Category",
            "message": f'"{top["category_name"]}" was your largest expense category at {top["share_pct"]:.0f}% of spending.',
        })

    # Biggest single expense
    if biggest:
        insights.append({
            "type": "info",
            "title": "Biggest Single Expense",
            "message": f'Your largest transaction was "{biggest["description"]}" for {biggest["amount"]:.2f}.',
        })

    # Rolling trend
    if len(trend) >= 3:
        expenses_trend = [w["expenses"] for w in trend]
        if all(expenses_trend[i] < expenses_trend[i + 1] for i in range(len(expenses_trend) - 1)):
            insights.append({
                "type": "warning",
                "title": "Rising Spending Trend",
                "message": "Your expenses have increased for 3 consecutive weeks.",
            })
        elif all(expenses_trend[i] > expenses_trend[i + 1] for i in range(len(expenses_trend) - 1)):
            insights.append({
                "type": "success",
                "title": "Declining Spending Trend",
                "message": "Your expenses have decreased for 3 consecutive weeks. Keep it up!",
            })

    return insights


def save_digest(user_id: int, summary: dict[str, Any]) -> WeeklyDigest:
    """Persist a generated digest to the database."""
    period = summary["period"]
    week_start = date.fromisoformat(period["week_start"])
    week_end = date.fromisoformat(period["week_end"])

    # Upsert: replace existing digest for the same week
    existing = (
        db.session.query(WeeklyDigest)
        .filter_by(user_id=user_id, week_start=week_start)
        .first()
    )
    if existing:
        existing.week_end = week_end
        existing.summary = summary
        existing.generated_at = datetime.utcnow()
        db.session.commit()
        return existing

    digest = WeeklyDigest(
        user_id=user_id,
        week_start=week_start,
        week_end=week_end,
        summary=summary,
    )
    db.session.add(digest)
    db.session.commit()
    return digest


def get_digest_history(user_id: int, limit: int = 12) -> list[dict[str, Any]]:
    """Return past weekly digests ordered newest-first."""
    digests = (
        db.session.query(WeeklyDigest)
        .filter_by(user_id=user_id)
        .order_by(WeeklyDigest.week_start.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": d.id,
            "week_start": d.week_start.isoformat(),
            "week_end": d.week_end.isoformat(),
            "generated_at": d.generated_at.isoformat() if d.generated_at else None,
            "summary": d.summary,
        }
        for d in digests
    ]
