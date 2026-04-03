"""
Guided Monthly Financial Review Flow (#102)
Creates a step-by-step monthly review experience with structured insights.
"""
from datetime import date, timedelta
from typing import Any
from decimal import Decimal
from ..extensions import db
from ..models import Expense, Category, Bill, RecurringExpense


# Review steps definition
REVIEW_STEPS = [
    {
        "id": "spending_overview",
        "title": "Spending Overview",
        "description": "How much did you spend this month vs last month?",
        "order": 1,
    },
    {
        "id": "category_breakdown",
        "title": "Category Breakdown",
        "description": "Where did your money go?",
        "order": 2,
    },
    {
        "id": "top_expenses",
        "title": "Top Expenses",
        "description": "Your largest individual transactions this month.",
        "order": 3,
    },
    {
        "id": "bills_status",
        "title": "Bills & Recurring",
        "description": "Review your regular commitments.",
        "order": 4,
    },
    {
        "id": "savings_check",
        "title": "Savings Check",
        "description": "Did you save anything this month?",
        "order": 5,
    },
    {
        "id": "action_items",
        "title": "Action Items",
        "description": "What should you do differently next month?",
        "order": 6,
    },
]


def _get_month_range(month: str):
    """Return start and end dates for a given YYYY-MM month string."""
    year, mo = int(month[:4]), int(month[5:7])
    start = date(year, mo, 1)
    if mo == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mo + 1, 1)
    return start, end


def _get_prev_month(month: str) -> str:
    """Return the previous month as YYYY-MM."""
    year, mo = int(month[:4]), int(month[5:7])
    if mo == 1:
        return f"{year - 1}-12"
    return f"{year}-{mo - 1:02d}"


def generate_monthly_review(user_id: int, month: str | None = None) -> dict[str, Any]:
    """
    Generate a complete guided monthly financial review.

    Args:
        user_id: The user ID to review
        month: Month in YYYY-MM format (defaults to last month)

    Returns:
        Structured review with steps, insights, and action items
    """
    if not month:
        today = date.today()
        if today.month == 1:
            month = f"{today.year - 1}-12"
        else:
            month = f"{today.year}-{today.month - 1:02d}"

    try:
        start_date, end_date = _get_month_range(month)
    except (ValueError, IndexError):
        today = date.today()
        if today.month == 1:
            month = f"{today.year - 1}-12"
        else:
            month = f"{today.year}-{today.month - 1:02d}"
        start_date, end_date = _get_month_range(month)

    prev_month = _get_prev_month(month)
    prev_start, prev_end = _get_month_range(prev_month)

    # Current month expenses
    curr_rows = (
        db.session.query(
            Expense.amount,
            Expense.spent_at,
            Expense.notes,
            Expense.expense_type,
            Category.name.label("category_name"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start_date,
            Expense.spent_at < end_date,
        )
        .all()
    )

    # Previous month expenses
    prev_rows = (
        db.session.query(Expense.amount, Expense.expense_type)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_start,
            Expense.spent_at < prev_end,
        )
        .all()
    )

    curr_expenses = [r for r in curr_rows if r.expense_type == "EXPENSE"]
    curr_income = [r for r in curr_rows if r.expense_type == "INCOME"]
    prev_expenses = [r for r in prev_rows if r.expense_type == "EXPENSE"]

    curr_total = float(sum(r.amount for r in curr_expenses))
    curr_income_total = float(sum(r.amount for r in curr_income))
    prev_total = float(sum(r.amount for r in prev_expenses))

    # Step 1: Spending Overview
    mom_change = ((curr_total - prev_total) / prev_total * 100) if prev_total > 0 else 0
    step1 = {
        **REVIEW_STEPS[0],
        "data": {
            "current_month_spend": round(curr_total, 2),
            "previous_month_spend": round(prev_total, 2),
            "month_over_month_change_pct": round(mom_change, 1),
            "trend": "up" if mom_change > 5 else "down" if mom_change < -5 else "stable",
        },
        "insight": (
            f"You spent {curr_total:.0f} this month, "
            f"{'up' if mom_change >= 0 else 'down'} {abs(mom_change):.1f}% vs last month."
            if prev_total > 0 else
            f"You spent {curr_total:.0f} this month."
        ),
        "status": "complete" if curr_rows else "no_data",
    }

    # Step 2: Category Breakdown
    cat_totals: dict[str, float] = {}
    for r in curr_expenses:
        cat = r.category_name or "Uncategorized"
        cat_totals[cat] = cat_totals.get(cat, 0.0) + float(r.amount)

    top_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:6]
    step2 = {
        **REVIEW_STEPS[1],
        "data": {
            "categories": [
                {
                    "name": cat,
                    "amount": round(amt, 2),
                    "pct": round(amt / curr_total * 100, 1) if curr_total > 0 else 0,
                }
                for cat, amt in top_cats
            ],
        },
        "insight": (
            f"Top category: {top_cats[0][0]} at {top_cats[0][1]:.0f} "
            f"({top_cats[0][1] / curr_total * 100:.0f}% of spending)."
            if top_cats else "No categorized expenses this month."
        ),
        "status": "complete" if curr_expenses else "no_data",
    }

    # Step 3: Top Individual Expenses
    sorted_expenses = sorted(curr_expenses, key=lambda r: float(r.amount), reverse=True)[:5]
    step3 = {
        **REVIEW_STEPS[2],
        "data": {
            "top_expenses": [
                {
                    "description": r.notes or "No description",
                    "category": r.category_name or "Uncategorized",
                    "amount": float(r.amount),
                    "date": r.spent_at.isoformat() if hasattr(r, "spent_at") else None,
                }
                for r in sorted_expenses
            ],
        },
        "insight": (
            f"Largest expense: {sorted_expenses[0].notes or 'Unknown'} "
            f"at {float(sorted_expenses[0].amount):.0f}."
            if sorted_expenses else "No expenses recorded this month."
        ),
        "status": "complete" if curr_expenses else "no_data",
    }

    # Step 4: Bills Status
    active_bills = (
        db.session.query(Bill)
        .filter(Bill.user_id == user_id, Bill.active == True)
        .all()
    )
    bill_total = float(sum(b.amount for b in active_bills))

    step4 = {
        **REVIEW_STEPS[3],
        "data": {
            "active_bills": len(active_bills),
            "total_recurring_monthly": round(bill_total, 2),
            "bills": [
                {"name": b.name, "amount": float(b.amount), "cadence": b.cadence.value}
                for b in active_bills[:5]
            ],
        },
        "insight": (
            f"You have {len(active_bills)} active bills totaling {bill_total:.0f}/month."
            if active_bills else "No active bills tracked."
        ),
        "status": "complete",
    }

    # Step 5: Savings Check
    net_position = curr_income_total - curr_total
    savings_rate = (net_position / curr_income_total * 100) if curr_income_total > 0 else None

    step5 = {
        **REVIEW_STEPS[4],
        "data": {
            "income_this_month": round(curr_income_total, 2),
            "expenses_this_month": round(curr_total, 2),
            "net_position": round(net_position, 2),
            "savings_rate_pct": round(savings_rate, 1) if savings_rate is not None else None,
            "saved": net_position > 0,
        },
        "insight": (
            f"Saved {net_position:.0f} ({savings_rate:.1f}% savings rate)."
            if savings_rate is not None and net_position > 0 else
            f"Spent {abs(net_position):.0f} more than earned." 
            if curr_income_total > 0 and net_position < 0 else
            "No income recorded. Add income transactions for savings tracking."
        ),
        "status": "complete" if curr_income_total > 0 else "no_income_data",
    }

    # Step 6: Action Items
    actions = []
    if mom_change > 15:
        actions.append({
            "priority": "high",
            "action": f"Review what caused the {mom_change:.0f}% spending increase vs last month.",
        })
    if top_cats and top_cats[0][1] / curr_total > 0.4 if curr_total > 0 else False:
        actions.append({
            "priority": "medium",
            "action": f"Diversify spending: {top_cats[0][0]} alone is >40% of budget.",
        })
    if savings_rate is not None and savings_rate < 10:
        actions.append({
            "priority": "high",
            "action": "Increase savings rate to at least 20% of income.",
        })
    if len(active_bills) == 0:
        actions.append({
            "priority": "low",
            "action": "Add your regular bills to track recurring commitments.",
        })
    if not actions:
        actions.append({
            "priority": "low",
            "action": "Great month! Keep maintaining current spending habits.",
        })

    step6 = {
        **REVIEW_STEPS[5],
        "data": {"actions": actions},
        "insight": f"{len(actions)} action item(s) for next month.",
        "status": "complete",
    }

    steps = [step1, step2, step3, step4, step5, step6]
    completed_steps = sum(1 for s in steps if s["status"] == "complete")

    return {
        "month": month,
        "review_steps": steps,
        "progress": {
            "completed": completed_steps,
            "total": len(steps),
            "pct": round(completed_steps / len(steps) * 100),
        },
        "summary": {
            "total_spend": round(curr_total, 2),
            "total_income": round(curr_income_total, 2),
            "net_position": round(curr_income_total - curr_total, 2),
            "expense_categories": len(cat_totals),
            "action_items": len(actions),
        },
    }
