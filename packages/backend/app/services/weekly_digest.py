"""
Smart weekly financial digest (issue #121 — $500 bounty).

Generates a personalized weekly summary with spending trends,
top categories, budget warnings, and actionable insights.
"""
import logging
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Category, Bill

logger = logging.getLogger("finmind.digest")


def _week_range(ref: Optional[date] = None):
    today = ref or date.today()
    # Monday to Sunday of the previous complete week
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def _prev_week_range(ref: Optional[date] = None):
    start, end = _week_range(ref)
    return start - timedelta(days=7), end - timedelta(days=7)


def generate_weekly_digest(user_id: int, ref_date: Optional[date] = None) -> dict:
    """
    Build weekly digest dict for a user.
    Returns structured summary ready for email/API/notification.
    """
    week_start, week_end = _week_range(ref_date)
    prev_start, prev_end = _prev_week_range(ref_date)

    def expense_total(start, end, expense_type="EXPENSE"):
        return float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= start,
                Expense.spent_at <= end,
                Expense.expense_type == expense_type,
            )
            .scalar() or 0
        )

    this_spend = expense_total(week_start, week_end)
    prev_spend = expense_total(prev_start, prev_end)
    this_income = expense_total(week_start, week_end, "INCOME")

    delta_pct = (
        round(((this_spend - prev_spend) / prev_spend) * 100, 1)
        if prev_spend > 0 else None
    )

    # Top categories this week
    cat_rows = (
        db.session.query(
            func.coalesce(Category.name, "Uncategorized").label("name"),
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(5)
        .all()
    )

    # Transaction count
    tx_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
        )
        .scalar() or 0
    )

    # Upcoming bills in next 7 days
    today = ref_date or date.today()
    upcoming = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date >= today,
            Bill.next_due_date <= today + timedelta(days=7),
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )

    # Insights
    insights = []
    if delta_pct is not None:
        if delta_pct > 20:
            insights.append(f"Spending up {delta_pct}% vs last week — review your top categories.")
        elif delta_pct < -10:
            insights.append(f"Great job! Spending down {abs(delta_pct)}% vs last week.")
    if this_income > 0 and this_spend > this_income:
        insights.append("You spent more than you earned this week.")
    if upcoming:
        names = ", ".join(b.name for b in upcoming[:3])
        insights.append(f"Bills due soon: {names}.")

    return {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
        },
        "summary": {
            "total_spent": round(this_spend, 2),
            "total_income": round(this_income, 2),
            "net": round(this_income - this_spend, 2),
            "transaction_count": int(tx_count),
            "vs_last_week_pct": delta_pct,
        },
        "top_categories": [
            {"name": r.name, "amount": float(r.total or 0)} for r in cat_rows
        ],
        "upcoming_bills": [
            {"name": b.name, "amount": float(b.amount), "due": b.next_due_date.isoformat()}
            for b in upcoming
        ],
        "insights": insights,
    }
