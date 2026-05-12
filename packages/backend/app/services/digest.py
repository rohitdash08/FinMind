"""Weekly financial digest service."""

from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Optional

from ..extensions import db
from ..models import User, Expense, Bill
import logging

logger = logging.getLogger("finmind.digest")


def generate_weekly_digest(user_id: int, end_date: Optional[date] = None) -> dict:
    """Generate a weekly financial summary for a user."""
    if not end_date:
        end_date = date.today()
    start_date = end_date - timedelta(days=7)
    prev_start = start_date - timedelta(days=7)

    user = db.session.get(User, user_id)
    if not user:
        return {"error": "user not found"}

    # Current week expenses
    current_expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
        )
        .all()
    )

    # Previous week for comparison
    prev_expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_start,
            Expense.spent_at < start_date,
        )
        .all()
    )

    current_total = sum(Decimal(str(e.amount)) for e in current_expenses)
    prev_total = sum(Decimal(str(e.amount)) for e in prev_expenses)

    # Category breakdown
    by_category = {}
    for e in current_expenses:
        cat = e.category_id or 0
        by_category.setdefault(cat, Decimal("0"))
        by_category[cat] += Decimal(str(e.amount))

    # Top spending category
    top_category = max(by_category, key=by_category.get) if by_category else None

    # Upcoming bills
    upcoming_bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active == True,
            Bill.next_due_date >= end_date,
            Bill.next_due_date <= end_date + timedelta(days=7),
        )
        .all()
    )

    # Trend
    if prev_total > 0:
        change_pct = float((current_total - prev_total) / prev_total * 100)
    else:
        change_pct = 0.0

    # Insights
    insights = []
    if change_pct > 20:
        insights.append(f"Spending increased {change_pct:.0f}% compared to last week")
    elif change_pct < -20:
        insights.append(f"Great job! Spending decreased {abs(change_pct):.0f}% compared to last week")

    if len(current_expenses) == 0:
        insights.append("No expenses recorded this week — consider logging your spending")

    if upcoming_bills:
        total_due = sum(float(b.amount) for b in upcoming_bills)
        insights.append(f"{len(upcoming_bills)} bill(s) due next week totaling {user.preferred_currency} {total_due:.2f}")

    return {
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "currency": user.preferred_currency,
        "summary": {
            "total_spent": float(current_total),
            "transaction_count": len(current_expenses),
            "daily_average": float(current_total / 7) if current_total else 0,
        },
        "comparison": {
            "previous_week_total": float(prev_total),
            "change_percent": round(change_pct, 1),
            "trend": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
        },
        "top_category_id": top_category,
        "category_breakdown": {str(k): float(v) for k, v in by_category.items()},
        "upcoming_bills": [
            {"name": b.name, "amount": float(b.amount), "due_date": b.next_due_date.isoformat()}
            for b in upcoming_bills
        ],
        "insights": insights,
    }
