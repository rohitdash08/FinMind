"""Weekly digest service -- aggregates expenses into a weekly summary."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func

from ..extensions import db
from ..models import Category, Expense


def _parse_week(week_str: str) -> tuple:
    """Parse ``YYYY-WNN`` into (monday, sunday) date range.

    Raises ``ValueError`` when the format is invalid.
    """
    parts = week_str.split("-W")
    if len(parts) != 2:
        raise ValueError("week must be YYYY-WNN")
    year = int(parts[0])
    week_num = int(parts[1])
    if week_num < 1 or week_num > 53:
        raise ValueError("week number must be between 01 and 53")
    monday = date.fromisocalendar(year, week_num, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def get_weekly_digest(user_id: int, week_str: str) -> dict:
    """Return a weekly financial digest for *user_id*.

    Parameters
    ----------
    user_id : int
        Authenticated user id.
    week_str : str
        ISO week in ``YYYY-WNN`` format, e.g. ``2026-W15``.
    """
    monday, sunday = _parse_week(week_str)

    # --- current week expenses ------------------------------------------------
    current_expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
        )
        .all()
    )

    total_spent = float(sum(Decimal(str(e.amount)) for e in current_expenses))

    # --- category breakdown ---------------------------------------------------
    cat_rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    category_breakdown = []
    for row in cat_rows:
        amount = float(row.total)
        pct = round((amount / total_spent) * 100, 1) if total_spent else 0.0
        category_breakdown.append(
            {
                "category_id": row.category_id,
                "category_name": row.category_name,
                "amount": amount,
                "percentage": pct,
            }
        )

    # --- previous week for week-over-week comparison --------------------------
    prev_monday = monday - timedelta(days=7)
    prev_sunday = sunday - timedelta(days=7)

    prev_total_row = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_monday,
            Expense.spent_at <= prev_sunday,
        )
        .scalar()
    )
    prev_total = float(prev_total_row or 0)

    if prev_total:
        wow_change = round(((total_spent - prev_total) / prev_total) * 100, 1)
    else:
        wow_change = 0.0 if total_spent == 0 else 100.0

    # --- trends ---------------------------------------------------------------
    trends = _compute_trends(total_spent, prev_total, category_breakdown)

    # --- insights -------------------------------------------------------------
    insights = _compute_insights(
        total_spent, prev_total, wow_change, category_breakdown
    )

    return {
        "week": week_str,
        "start_date": monday.isoformat(),
        "end_date": sunday.isoformat(),
        "total_spent": total_spent,
        "category_breakdown": category_breakdown,
        "week_over_week_change": wow_change,
        "previous_week_total": prev_total,
        "trends": trends,
        "insights": insights,
        "transaction_count": len(current_expenses),
    }


def _compute_trends(total, prev_total, categories):
    trends = []
    if total > prev_total and prev_total > 0:
        trends.append("Spending increased compared to last week")
    elif total < prev_total:
        trends.append("Spending decreased compared to last week")
    elif prev_total == 0 and total > 0:
        trends.append("First week of tracked spending")
    else:
        trends.append("Spending remained the same as last week")

    if categories:
        top = categories[0]
        trends.append(
            f"Top spending category: {top['category_name']} "
            f"({top['percentage']}% of total)"
        )

    return trends


def _compute_insights(total, prev_total, wow_change, categories):
    insights = []

    if wow_change > 20:
        insights.append(
            f"Spending jumped {wow_change}% week-over-week. "
            "Review recent transactions for unexpected charges."
        )
    elif wow_change < -20:
        insights.append(
            f"Great job! Spending dropped {abs(wow_change)}% from last week."
        )

    if len(categories) >= 1:
        top = categories[0]
        if top["percentage"] > 50:
            insights.append(
                f"{top['category_name']} accounts for over half your spending. "
                "Consider diversifying or setting a cap."
            )

    if total == 0:
        insights.append("No spending recorded this week.")

    if not insights:
        insights.append("Spending looks steady. Keep it up!")

    return insights
