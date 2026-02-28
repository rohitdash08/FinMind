"""Weekly summary service for generating financial digests."""
from datetime import date, timedelta
from sqlalchemy import func
from typing import TypedDict

from ..extensions import db
from ..models import Expense, Category


class WeekComparison(TypedDict):
    current_week: float
    previous_week: float
    change_pct: float


class CategorySpend(TypedDict):
    category_id: int | None
    category_name: str
    amount: float
    percentage: float


class TopExpense(TypedDict):
    id: int
    amount: float
    description: str
    date: str
    category_name: str


class WeeklySummary(TypedDict):
    week_start: str
    week_end: str
    total_spent: float
    total_income: float
    net_flow: float
    comparison: WeekComparison
    category_breakdown: list[CategorySpend]
    top_expenses: list[TopExpense]
    insights: list[str]


def _get_week_boundaries(target_date: date) -> tuple[date, date]:
    """Get start (Monday) and end (Sunday) of the week containing target_date."""
    # weekday(): Monday=0, Sunday=6
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _get_week_totals(uid: int, week_start: date, week_end: date) -> tuple[float, float]:
    """Get total income and expenses for a week."""
    income_result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    
    expense_result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    
    return float(income_result or 0), float(expense_result or 0)


def _get_category_breakdown(uid: int, week_start: date, week_end: date) -> list[CategorySpend]:
    """Get spending breakdown by category for the week."""
    total_spent = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    ) or 0
    
    if total_spent == 0:
        return []
    
    rows = (
        db.session.query(
            Expense.category_id,
            Category.name,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    
    return [
        {
            "category_id": cat_id,
            "category_name": cat_name or "Uncategorized",
            "amount": round(float(amount), 2),
            "percentage": round((float(amount) / total_spent) * 100, 1),
        }
        for cat_id, cat_name, amount in rows
    ]


def _get_top_expenses(uid: int, week_start: date, week_end: date, limit: int = 5) -> list[TopExpense]:
    """Get top expenses for the week."""
    expenses = (
        db.session.query(
            Expense.id,
            Expense.amount,
            Expense.notes,
            Expense.spent_at,
            Category.name,
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .limit(limit)
        .all()
    )
    
    return [
        {
            "id": exp_id,
            "amount": float(amount),
            "description": notes or "",
            "date": spent_at.isoformat(),
            "category_name": cat_name or "Uncategorized",
        }
        for exp_id, amount, notes, spent_at, cat_name in expenses
    ]


def _generate_insights(
    current_spent: float,
    previous_spent: float,
    category_breakdown: list[CategorySpend],
    net_flow: float,
) -> list[str]:
    """Generate personalized insights based on weekly data."""
    insights = []
    
    # Week-over-week comparison
    if previous_spent > 0:
        change_pct = ((current_spent - previous_spent) / previous_spent) * 100
        if change_pct > 20:
            insights.append(f"Your spending increased by {change_pct:.1f}% compared to last week. Consider reviewing your expenses.")
        elif change_pct < -20:
            insights.append(f"Great job! Your spending decreased by {abs(change_pct):.1f}% from last week.")
    
    # Category insights
    if category_breakdown:
        top_category = category_breakdown[0]
        insights.append(f"{top_category['category_name']} was your top spending category at {top_category['percentage']}% of total.")
    
    # Net flow insight
    if net_flow < 0:
        insights.append(f"You spent ₹{abs(net_flow):.2f} more than you earned this week. Try to reduce discretionary spending.")
    elif net_flow > 0:
        insights.append(f"You saved ₹{net_flow:.2f} this week! Consider adding this to your emergency fund or investments.")
    
    # Add general tips if few insights
    if len(insights) < 2:
        insights.append("Track your daily expenses to build better financial habits.")
    
    return insights


def generate_weekly_summary(uid: int, target_date: date | None = None) -> WeeklySummary:
    """Generate a comprehensive weekly financial summary for a user.
    
    Args:
        uid: User ID
        target_date: Date within the target week (defaults to today)
        
    Returns:
        WeeklySummary with trends, insights, and breakdowns
    """
    if target_date is None:
        target_date = date.today()
    
    # Get current week boundaries
    week_start, week_end = _get_week_boundaries(target_date)
    
    # Get previous week for comparison
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_end - timedelta(days=7)
    
    # Get totals
    current_income, current_spent = _get_week_totals(uid, week_start, week_end)
    previous_income, previous_spent = _get_week_totals(uid, prev_week_start, prev_week_end)
    
    # Calculate comparison
    if previous_spent > 0:
        change_pct = round(((current_spent - previous_spent) / previous_spent) * 100, 2)
    else:
        change_pct = 0.0 if current_spent == 0 else 100.0
    
    # Get breakdowns
    category_breakdown = _get_category_breakdown(uid, week_start, week_end)
    top_expenses = _get_top_expenses(uid, week_start, week_end)
    
    # Generate insights
    net_flow = current_income - current_spent
    insights = _generate_insights(current_spent, previous_spent, category_breakdown, net_flow)
    
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_spent": round(current_spent, 2),
        "total_income": round(current_income, 2),
        "net_flow": round(net_flow, 2),
        "comparison": {
            "current_week": round(current_spent, 2),
            "previous_week": round(previous_spent, 2),
            "change_pct": change_pct,
        },
        "category_breakdown": category_breakdown,
        "top_expenses": top_expenses,
        "insights": insights,
    }
