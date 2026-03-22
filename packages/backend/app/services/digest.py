"""Weekly financial digest service.

Generates weekly summaries highlighting spending trends, category insights,
and actionable recommendations.
"""

from datetime import date, timedelta

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense, Category


def _week_boundaries(ref: date | None = None) -> tuple[date, date]:
    """Return (start, end) of the previous full ISO week."""
    today = ref or date.today()
    # ISO weekday: Monday=1, Sunday=7
    days_since_monday = today.isoweekday() - 1
    this_monday = today - timedelta(days=days_since_monday)
    prev_monday = this_monday - timedelta(weeks=1)
    prev_sunday = this_monday - timedelta(days=1)
    return prev_monday, prev_sunday


def _week_totals(
    uid: int, start: date, end: date
) -> tuple[float, float]:
    """Sum income and expenses for a date range."""
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


def _category_breakdown(uid: int, start: date, end: date) -> list[dict]:
    """Category-level expense breakdown for a date range."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("count"),
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
            "category_name": r.name,
            "amount": round(float(r.total or 0), 2),
            "transaction_count": r.count,
            "share_pct": (
                round((float(r.total or 0) / total_spend) * 100, 2)
                if total_spend > 0
                else 0
            ),
        }
        for r in rows
    ]


def _daily_spending(uid: int, start: date, end: date) -> list[dict]:
    """Daily expense totals for a date range."""
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
    return [
        {"date": r.spent_at.isoformat(), "amount": round(float(r.total or 0), 2)}
        for r in rows
    ]


def _generate_insights(
    current_income: float,
    current_expenses: float,
    prev_income: float,
    prev_expenses: float,
    categories: list[dict],
) -> list[str]:
    """Generate actionable text insights from the data."""
    insights = []

    # Week-over-week spending trend
    if prev_expenses > 0:
        pct_change = ((current_expenses - prev_expenses) / prev_expenses) * 100
        if pct_change > 10:
            insights.append(
                f"Your spending increased by {pct_change:.1f}% compared to the "
                "previous week. Review discretionary purchases."
            )
        elif pct_change < -10:
            insights.append(
                f"Great job! Your spending decreased by {abs(pct_change):.1f}% "
                "compared to the previous week."
            )
        else:
            insights.append("Your spending is roughly stable week-over-week.")
    else:
        insights.append("No previous week data to compare.")

    # Net flow
    net = current_income - current_expenses
    if net < 0:
        insights.append(
            f"You spent more than you earned this week (net: {net:.2f}). "
            "Consider cutting non-essential expenses."
        )
    elif net > 0:
        insights.append(
            f"Positive cash flow this week: +{net:.2f}. "
            "Consider saving or investing the surplus."
        )

    # Top category
    if categories:
        top = categories[0]
        insights.append(
            f"Highest spending category: {top['category_name']} "
            f"({top['share_pct']:.0f}% of total). "
            "Look for ways to optimise here."
        )

    return insights


def weekly_digest(uid: int, ref_date: date | None = None) -> dict:
    """Build the full weekly financial digest for a user.

    Args:
        uid: User ID.
        ref_date: Reference date (defaults to today). The digest covers
                  the *previous* full Monday-Sunday week relative to this date.

    Returns:
        Dictionary with period, summary, category_breakdown, daily_spending,
        and insights.
    """
    start, end = _week_boundaries(ref_date)

    # Previous week for comparison
    prev_start = start - timedelta(weeks=1)
    prev_end = end - timedelta(weeks=1)

    current_income, current_expenses = _week_totals(uid, start, end)
    prev_income, prev_expenses = _week_totals(uid, prev_start, prev_end)

    categories = _category_breakdown(uid, start, end)
    daily = _daily_spending(uid, start, end)
    transaction_count = sum(c["transaction_count"] for c in categories)

    wow_change_pct = 0.0
    if prev_expenses > 0:
        wow_change_pct = round(
            ((current_expenses - prev_expenses) / prev_expenses) * 100, 2
        )

    insights = _generate_insights(
        current_income, current_expenses, prev_income, prev_expenses, categories
    )

    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "type": "weekly",
        },
        "summary": {
            "total_income": round(current_income, 2),
            "total_expenses": round(current_expenses, 2),
            "net_flow": round(current_income - current_expenses, 2),
            "transaction_count": transaction_count,
            "week_over_week_change_pct": wow_change_pct,
            "previous_week_expenses": round(prev_expenses, 2),
        },
        "category_breakdown": categories,
        "daily_spending": daily,
        "insights": insights,
    }
