"""Weekly financial digest service.

Generates smart weekly summaries highlighting trends and insights for a user's
financial activity over the past 7 days. Includes:
- Week-over-week spending change
- Top spending categories
- Biggest single transaction
- Income vs. expense ratio
- Bill reminders for the upcoming week
- Savings rate
- Actionable tips
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Bill, Category, Expense


def _week_bounds(reference_date: date | None = None) -> tuple[date, date]:
    """Return (start, end) for the ISO week containing *reference_date*.

    Week runs Monday–Sunday.  If *reference_date* is None, uses today.
    """
    ref = reference_date or date.today()
    start = ref - timedelta(days=ref.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start, end


def _previous_week_bounds(start: date) -> tuple[date, date]:
    """Return the week bounds for the week before *start*."""
    prev_monday = start - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def _totals_in_range(
    uid: int, from_date: date, to_date: date
) -> tuple[float, float]:
    """Return (income, expenses) for *uid* between *from_date* and *to_date* inclusive."""
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= from_date,
            Expense.spent_at <= to_date,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= from_date,
            Expense.spent_at <= to_date,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _category_breakdown(
    uid: int, from_date: date, to_date: date
) -> list[dict[str, Any]]:
    """Return expense breakdown by category for the given date range."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
            func.count(Expense.id).label("tx_count"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= from_date,
            Expense.spent_at <= to_date,
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
            "amount": float(r.total_amount or 0),
            "transaction_count": int(r.tx_count or 0),
            "share_pct": (
                round((float(r.total_amount or 0) / total) * 100, 2)
                if total > 0
                else 0.0
            ),
        }
        for r in rows
    ]


def _biggest_transaction(
    uid: int, from_date: date, to_date: date
) -> dict[str, Any] | None:
    """Return the single largest expense in the date range."""
    row = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= from_date,
            Expense.spent_at <= to_date,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .first()
    )
    if not row:
        return None
    return {
        "id": row.id,
        "description": row.notes or "Transaction",
        "amount": float(row.amount),
        "currency": row.currency,
        "date": row.spent_at.isoformat(),
        "category_id": row.category_id,
    }


def _upcoming_bills(uid: int, from_date: date, to_date: date) -> list[dict[str, Any]]:
    """Return bills due in the upcoming week."""
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= from_date,
            Bill.next_due_date <= to_date,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
        }
        for b in bills
    ]


def _daily_spending(uid: int, from_date: date, to_date: date) -> list[dict[str, Any]]:
    """Return daily spending totals for the week."""
    rows = (
        db.session.query(
            Expense.spent_at.label("day"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= from_date,
            Expense.spent_at <= to_date,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at.asc())
        .all()
    )
    spending_map = {r.day: float(r.total or 0) for r in rows}
    daily = []
    current = from_date
    while current <= to_date:
        daily.append({"date": current.isoformat(), "amount": spending_map.get(current, 0.0)})
        current += timedelta(days=1)
    return daily


def _generate_tips(
    current_expenses: float,
    previous_expenses: float,
    savings_rate: float,
    top_categories: list[dict[str, Any]],
    income: float,
) -> list[str]:
    """Generate actionable tips based on the user's weekly financial data."""
    tips: list[str] = []

    # Spending trend tip
    if previous_expenses > 0:
        wow_change = ((current_expenses - previous_expenses) / previous_expenses) * 100
        if wow_change > 20:
            tips.append(
                f"Your spending is up {wow_change:.0f}% compared to last week. "
                "Review discretionary purchases to get back on track."
            )
        elif wow_change < -10:
            tips.append(
                f"Great job! You spent {abs(wow_change):.0f}% less than last week. "
                "Keep the momentum going."
            )
    else:
        if current_expenses > 0:
            tips.append(
                "No spending data from last week to compare against. "
                "Keep tracking to build trend insights."
            )

    # Savings rate tip
    if income > 0:
        if savings_rate < 10:
            tips.append(
                "Your savings rate is below 10% this week. Try the 50/30/20 rule: "
                "50% needs, 30% wants, 20% savings."
            )
        elif savings_rate >= 20:
            tips.append(
                f"You're saving {savings_rate:.0f}% of your income this week — solid discipline!"
            )

    # Top category tip
    if top_categories:
        top = top_categories[0]
        if top["share_pct"] > 50:
            tips.append(
                f"Over half your spending ({top['share_pct']:.0f}%) went to "
                f"'{top['category_name']}'. See if you can reduce it by 10% next week."
            )

    # Default tip if none generated
    if not tips:
        tips.append("Set a weekly spending limit and review your progress every Sunday.")

    return tips


def generate_weekly_digest(
    uid: int,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Generate a smart weekly financial digest for user *uid*.

    Args:
        uid: The user ID.
        reference_date: The reference date (defaults to today). The digest
            covers the ISO week (Mon–Sun) that contains this date.

    Returns:
        A dict with the weekly summary, trends, insights, and tips.
    """
    ref = reference_date or date.today()
    week_start, week_end = _week_bounds(ref)
    prev_start, prev_end = _previous_week_bounds(week_start)

    # Current week data
    current_income, current_expenses = _totals_in_range(uid, week_start, week_end)

    # Previous week data
    previous_income, previous_expenses = _totals_in_range(uid, prev_start, prev_end)

    # Week-over-week change
    if previous_expenses > 0:
        wow_change_pct = round(
            ((current_expenses - previous_expenses) / previous_expenses) * 100, 2
        )
    else:
        wow_change_pct = 0.0

    # Income vs. expense ratio
    if current_expenses > 0 and current_income > 0:
        income_expense_ratio = round(current_income / current_expenses, 2)
    else:
        income_expense_ratio = 0.0

    # Savings rate
    if current_income > 0:
        savings_rate = round(
            max(0, ((current_income - current_expenses) / current_income) * 100), 2
        )
    else:
        savings_rate = 0.0

    # Net flow
    net_flow = round(current_income - current_expenses, 2)

    # Category breakdown
    categories = _category_breakdown(uid, week_start, week_end)

    # Biggest transaction
    biggest = _biggest_transaction(uid, week_start, week_end)

    # Upcoming bills (next 7 days from reference date)
    upcoming_start = ref + timedelta(days=1)
    upcoming_end = ref + timedelta(days=7)
    upcoming_bills = _upcoming_bills(uid, upcoming_start, upcoming_end)
    upcoming_bills_total = round(sum(b["amount"] for b in upcoming_bills), 2)

    # Daily spending pattern
    daily_spending = _daily_spending(uid, week_start, week_end)

    # Transaction count
    tx_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
        )
        .scalar()
    ) or 0

    # Generate tips
    tips = _generate_tips(
        current_expenses=current_expenses,
        previous_expenses=previous_expenses,
        savings_rate=savings_rate,
        top_categories=categories[:3],
        income=current_income,
    )

    return {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "reference_date": ref.isoformat(),
        },
        "summary": {
            "income": current_income,
            "expenses": current_expenses,
            "net_flow": net_flow,
            "savings_rate_pct": savings_rate,
            "income_expense_ratio": income_expense_ratio,
            "transaction_count": tx_count,
        },
        "trends": {
            "week_over_week_change_pct": wow_change_pct,
            "previous_week_expenses": previous_expenses,
            "previous_week_income": previous_income,
        },
        "top_categories": categories[:5],
        "biggest_transaction": biggest,
        "daily_spending": daily_spending,
        "upcoming_bills": upcoming_bills,
        "upcoming_bills_total": upcoming_bills_total,
        "tips": tips,
    }
