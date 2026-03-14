"""Weekly financial digest service.

Generates a comprehensive weekly financial summary including:
- Week spending vs income
- Category breakdown
- Week-over-week trend comparison
- Insights and anomalies
"""

from datetime import date, timedelta
from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense, Category


def _week_range(ref_date: date | None = None) -> tuple[date, date]:
    """Return (monday, sunday) for the week containing ref_date (default today)."""
    today = ref_date or date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _previous_week_range(monday: date) -> tuple[date, date]:
    """Return (monday, sunday) for the week immediately before the given monday."""
    prev_monday = monday - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def _week_totals(
    uid: int, start: date, end: date
) -> tuple[float, float]:
    """Return (income, expenses) for a user in a date range."""
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
    """Return category spending breakdown for a date range."""
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
            "amount": round(float(r.total_amount or 0), 2),
            "share_pct": (
                round((float(r.total_amount or 0) / total) * 100, 2)
                if total > 0
                else 0
            ),
        }
        for r in rows
    ]


def _generate_insights(
    current_income: float,
    current_expenses: float,
    prev_income: float,
    prev_expenses: float,
    categories: list[dict],
) -> list[str]:
    """Generate human-readable insights from the data."""
    insights = []

    # Net flow insight
    net = current_income - current_expenses
    prev_net = prev_income - prev_expenses
    if net > 0 and prev_net <= 0:
        insights.append("You're in the green this week — income exceeds expenses!")
    elif net < 0:
        burn = abs(net)
        if prev_expenses > 0 and current_expenses > prev_expenses:
            pct = round(((current_expenses - prev_expenses) / prev_expenses) * 100, 1)
            insights.append(
                f"Spending up {pct}% vs last week. Biggest driver: {categories[0]['category_name'] if categories else 'unknown'}."
            )
        else:
            insights.append(f"You spent {burn:.2f} more than you earned this week.")

    # Category concentration
    if categories and len(categories) >= 1:
        top = categories[0]
        if top["share_pct"] > 50:
            insights.append(
                f"{top['category_name']} is {top['share_pct']}% of your week's spending — consider diversifying."
            )

    # Savings rate
    if current_income > 0:
        savings_rate = round(((current_income - current_expenses) / current_income) * 100, 1)
        if savings_rate > 30:
            insights.append(f"Great savings rate: {savings_rate}% this week.")
        elif savings_rate < 0:
            insights.append(f"Negative savings rate ({savings_rate}%) — expenses outpacing income.")

    if not insights:
        insights.append("Quiet week financially. Keep tracking to build trends.")

    return insights


def generate_weekly_digest(
    uid: int, week_start: date | None = None
) -> dict:
    """Generate a complete weekly financial digest for a user.

    Args:
        uid: User ID
        week_start: Monday of the target week (defaults to current week)

    Returns:
        Dict with digest data including summary, categories, trends, insights
    """
    if week_start is None:
        week_start, _ = _week_range()
    else:
        # Ensure given date is a Monday
        week_start = week_start - timedelta(days=week_start.weekday())

    week_end = week_start + timedelta(days=6)
    prev_start, prev_end = _previous_week_range(week_start)

    current_income, current_expenses = _week_totals(uid, week_start, week_end)
    prev_income, prev_expenses = _week_totals(uid, prev_start, prev_end)
    categories = _category_breakdown(uid, week_start, week_end)

    # Week-over-week change
    if prev_expenses > 0:
        spending_wow_pct = round(
            ((current_expenses - prev_expenses) / prev_expenses) * 100, 2
        )
    else:
        spending_wow_pct = 0.0 if current_expenses == 0 else 100.0

    insights = _generate_insights(
        current_income, current_expenses, prev_income, prev_expenses, categories
    )

    return {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "label": f"Week of {week_start.strftime('%b %d, %Y')}",
        },
        "summary": {
            "income": round(current_income, 2),
            "expenses": round(current_expenses, 2),
            "net": round(current_income - current_expenses, 2),
            "transaction_count": _transaction_count(uid, week_start, week_end),
        },
        "trends": {
            "spending_wow_change_pct": spending_wow_pct,
            "previous_week_expenses": round(prev_expenses, 2),
            "previous_week_income": round(prev_income, 2),
            "previous_week_net": round(prev_income - prev_expenses, 2),
        },
        "categories": categories,
        "insights": insights,
    }


def _transaction_count(uid: int, start: date, end: date) -> int:
    """Count transactions in a date range."""
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
