"""Guided monthly financial review service.

Generates step-by-step monthly review insights covering spending,
categories, bills, recurring expenses, and trends.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, extract

from app.extensions import db
from app.models import Expense, Category, Bill, RecurringExpense


# ── Monthly Review Steps ──────────────────────────────────────────


def get_review(user_id: int, year: int, month: int) -> dict:
    """Generate a complete monthly financial review.

    Returns a step-by-step review with:
    1. Spending summary
    2. Category breakdown
    3. Top expenses
    4. Bill summary
    5. Recurring expense summary
    6. Month-over-month comparison
    7. Actionable insights
    """
    return {
        "year": year,
        "month": month,
        "steps": [
            _step_spending_summary(user_id, year, month),
            _step_category_breakdown(user_id, year, month),
            _step_top_expenses(user_id, year, month),
            _step_bill_summary(user_id, year, month),
            _step_recurring_summary(user_id, year, month),
            _step_month_comparison(user_id, year, month),
            _step_insights(user_id, year, month),
        ],
    }


def get_review_step(user_id: int, year: int, month: int, step: int) -> dict:
    """Get a single review step (1-indexed)."""
    step_fns = [
        _step_spending_summary,
        _step_category_breakdown,
        _step_top_expenses,
        _step_bill_summary,
        _step_recurring_summary,
        _step_month_comparison,
        _step_insights,
    ]
    if step < 1 or step > len(step_fns):
        return {"error": f"Invalid step {step}. Valid: 1-{len(step_fns)}"}
    return step_fns[step - 1](user_id, year, month)


def get_available_months(user_id: int) -> list:
    """Get list of months that have expense data for review."""
    results = (
        db.session.query(
            extract("year", Expense.spent_at).label("year"),
            extract("month", Expense.spent_at).label("month"),
        )
        .filter_by(user_id=user_id)
        .group_by("year", "month")
        .order_by(db.desc("year"), db.desc("month"))
        .all()
    )
    return [{"year": int(r.year), "month": int(r.month)} for r in results]


# ── Step Implementations ──────────────────────────────────────────


def _step_spending_summary(user_id: int, year: int, month: int) -> dict:
    """Step 1: Total spending summary."""
    expenses = _get_month_expenses(user_id, year, month)

    total = sum(float(e.amount) for e in expenses)
    count = len(expenses)
    avg = round(total / count, 2) if count else 0
    income_expenses = [e for e in expenses if e.expense_type == "INCOME"]
    expense_expenses = [e for e in expenses if e.expense_type != "INCOME"]

    total_income = sum(float(e.amount) for e in income_expenses)
    total_spending = sum(float(e.amount) for e in expense_expenses)

    return {
        "step": 1,
        "title": "Spending Summary",
        "description": "Overview of your monthly spending",
        "data": {
            "total_spending": round(total_spending, 2),
            "total_income": round(total_income, 2),
            "net": round(total_income - total_spending, 2),
            "transaction_count": count,
            "average_transaction": avg,
            "highest_single": round(max((float(e.amount) for e in expense_expenses), default=0), 2),
            "lowest_single": round(min((float(e.amount) for e in expense_expenses), default=0), 2),
        },
    }


def _step_category_breakdown(user_id: int, year: int, month: int) -> dict:
    """Step 2: Spending by category."""
    expenses = _get_month_expenses(user_id, year, month)
    expense_only = [e for e in expenses if e.expense_type != "INCOME"]

    category_totals = {}
    for e in expense_only:
        cat_name = "Uncategorized"
        if e.category_id:
            cat = Category.query.get(e.category_id)
            if cat:
                cat_name = cat.name
        category_totals[cat_name] = category_totals.get(cat_name, 0) + float(e.amount)

    total = sum(category_totals.values()) or 1
    categories = sorted(
        [
            {
                "category": name,
                "amount": round(amt, 2),
                "percentage": round(amt / total * 100, 1),
            }
            for name, amt in category_totals.items()
        ],
        key=lambda x: x["amount"],
        reverse=True,
    )

    return {
        "step": 2,
        "title": "Category Breakdown",
        "description": "Where your money went",
        "data": {
            "categories": categories,
            "top_category": categories[0]["category"] if categories else None,
            "category_count": len(categories),
        },
    }


def _step_top_expenses(user_id: int, year: int, month: int) -> dict:
    """Step 3: Largest individual expenses."""
    expenses = _get_month_expenses(user_id, year, month)
    expense_only = [e for e in expenses if e.expense_type != "INCOME"]

    sorted_expenses = sorted(expense_only, key=lambda e: float(e.amount), reverse=True)
    top = sorted_expenses[:10]

    return {
        "step": 3,
        "title": "Top Expenses",
        "description": "Your largest purchases this month",
        "data": {
            "expenses": [
                {
                    "id": e.id,
                    "amount": float(e.amount),
                    "notes": e.notes,
                    "spent_at": e.spent_at.isoformat() if e.spent_at else None,
                    "currency": e.currency,
                }
                for e in top
            ],
        },
    }


def _step_bill_summary(user_id: int, year: int, month: int) -> dict:
    """Step 4: Bills due this month."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    bills = Bill.query.filter(
        Bill.user_id == user_id,
        Bill.next_due_date >= start,
        Bill.next_due_date < end,
    ).all()

    total = sum(float(b.amount) for b in bills)
    paid = [b for b in bills if b.autopay_enabled]
    unpaid = [b for b in bills if not b.autopay_enabled]

    return {
        "step": 4,
        "title": "Bill Summary",
        "description": "Bills due this month",
        "data": {
            "total_bills": round(total, 2),
            "bill_count": len(bills),
            "autopay_count": len(paid),
            "manual_count": len(unpaid),
            "bills": [
                {
                    "id": b.id,
                    "name": b.name,
                    "amount": float(b.amount),
                    "due_date": b.next_due_date.isoformat(),
                    "autopay": b.autopay_enabled,
                }
                for b in bills
            ],
        },
    }


def _step_recurring_summary(user_id: int, year: int, month: int) -> dict:
    """Step 5: Active recurring expenses."""
    recurring = RecurringExpense.query.filter_by(
        user_id=user_id, active=True
    ).all()

    total_monthly = 0
    items = []
    for r in recurring:
        monthly = float(r.amount)
        if r.cadence.value == "YEARLY":
            monthly = monthly / 12
        elif r.cadence.value == "WEEKLY":
            monthly = monthly * 4
        elif r.cadence.value == "DAILY":
            monthly = monthly * 30

        total_monthly += monthly
        items.append({
            "id": r.id,
            "notes": r.notes,
            "amount": float(r.amount),
            "cadence": r.cadence.value,
            "monthly_equivalent": round(monthly, 2),
        })

    return {
        "step": 5,
        "title": "Recurring Expenses",
        "description": "Your ongoing commitments",
        "data": {
            "total_monthly": round(total_monthly, 2),
            "count": len(items),
            "items": sorted(items, key=lambda x: x["monthly_equivalent"], reverse=True),
        },
    }


def _step_month_comparison(user_id: int, year: int, month: int) -> dict:
    """Step 6: Compare with previous month."""
    current_expenses = _get_month_expenses(user_id, year, month)
    current_total = sum(float(e.amount) for e in current_expenses if e.expense_type != "INCOME")

    # Previous month
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    prev_expenses = _get_month_expenses(user_id, prev_year, prev_month)
    prev_total = sum(float(e.amount) for e in prev_expenses if e.expense_type != "INCOME")

    change = current_total - prev_total
    change_pct = round((change / prev_total * 100), 1) if prev_total else 0

    return {
        "step": 6,
        "title": "Month-over-Month",
        "description": "How this month compares to last",
        "data": {
            "current_month_total": round(current_total, 2),
            "previous_month_total": round(prev_total, 2),
            "change_amount": round(change, 2),
            "change_pct": change_pct,
            "trend": "up" if change > 0 else "down" if change < 0 else "flat",
        },
    }


def _step_insights(user_id: int, year: int, month: int) -> dict:
    """Step 7: Actionable insights and recommendations."""
    expenses = _get_month_expenses(user_id, year, month)
    expense_only = [e for e in expenses if e.expense_type != "INCOME"]

    insights = []

    # Insight: High spending day
    day_totals = {}
    for e in expense_only:
        if e.spent_at:
            day = e.spent_at.day
            day_totals[day] = day_totals.get(day, 0) + float(e.amount)

    if day_totals:
        peak_day = max(day_totals, key=day_totals.get)
        insights.append({
            "type": "peak_spending_day",
            "message": f"Your highest spending day was the {peak_day}th with ${day_totals[peak_day]:.2f}",
            "value": round(day_totals[peak_day], 2),
        })

    # Insight: Category concentration
    cat_totals = {}
    total_spent = sum(float(e.amount) for e in expense_only)
    for e in expense_only:
        cat_id = e.category_id or 0
        cat_totals[cat_id] = cat_totals.get(cat_id, 0) + float(e.amount)

    if cat_totals and total_spent:
        top_cat_pct = max(cat_totals.values()) / total_spent * 100
        if top_cat_pct > 50:
            insights.append({
                "type": "category_concentration",
                "message": f"Over {top_cat_pct:.0f}% of spending is in one category — consider diversifying",
                "value": round(top_cat_pct, 1),
            })

    # Insight: Transaction frequency
    if len(expense_only) > 0:
        avg_per_day = len(expense_only) / 30
        if avg_per_day > 3:
            insights.append({
                "type": "high_frequency",
                "message": f"Averaging {avg_per_day:.1f} transactions/day — small purchases add up",
                "value": round(avg_per_day, 1),
            })

    # Insight: Weekend vs weekday
    weekend = sum(float(e.amount) for e in expense_only if e.spent_at and e.spent_at.weekday() >= 5)
    weekday = sum(float(e.amount) for e in expense_only if e.spent_at and e.spent_at.weekday() < 5)
    if weekend > 0 and weekday > 0:
        ratio = weekend / (weekend + weekday) * 100
        if ratio > 40:
            insights.append({
                "type": "weekend_spending",
                "message": f"{ratio:.0f}% of spending happens on weekends",
                "value": round(ratio, 1),
            })

    return {
        "step": 7,
        "title": "Insights & Recommendations",
        "description": "Key takeaways from this month",
        "data": {
            "insights": insights,
            "insight_count": len(insights),
        },
    }


# ── Helpers ───────────────────────────────────────────────────────


def _get_month_expenses(user_id: int, year: int, month: int) -> list:
    """Get all expenses for a given month."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    return Expense.query.filter(
        Expense.user_id == user_id,
        Expense.spent_at >= start,
        Expense.spent_at < end,
    ).all()
