from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category, Bill, RecurringExpense


def _get_week_range(reference_date: Optional[date] = None):
    """Return (start, end) of the ISO week containing reference_date."""
    ref = reference_date or date.today()
    start = ref - timedelta(days=ref.weekday())   # Monday
    end = start + timedelta(days=6)               # Sunday
    return start, end


def _get_prev_week_range(reference_date: Optional[date] = None):
    ref = reference_date or date.today()
    start, _ = _get_week_range(ref)
    prev_start = start - timedelta(days=7)
    prev_end = prev_start + timedelta(days=6)
    return prev_start, prev_end


def compute_weekly_digest(user_id: int, reference_date: Optional[date] = None):
    """
    Generate a weekly financial summary for *user_id*.

    Returns a dict with:
      - week_start / week_end (ISO strings)
      - total_spent (float)
      - total_income (float)
      - net (float)
      - category_breakdown (list of {name, amount, pct_of_total})
      - top_expense (dict or None)
      - week_over_week_change (float, percent)
      - upcoming_bills (list of {name, due_date, amount})
      - insights (list of str)
    """
    start, end = _get_week_range(reference_date)
    prev_start, prev_end = _get_prev_week_range(reference_date)

    # --- current week expenses / income ---
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .all()
    )

    total_spent = sum(float(r.amount) for r in rows if r.expense_type == "EXPENSE")
    total_income = sum(float(r.amount) for r in rows if r.expense_type == "INCOME")
    net = total_income - total_spent

    # --- category breakdown ---
    cat_totals: dict[str, float] = {}
    for r in rows:
        if r.expense_type != "EXPENSE":
            continue
        cat_name = "Uncategorised"
        if r.category_id:
            cat = db.session.get(Category, r.category_id)
            if cat:
                cat_name = cat.name
        cat_totals[cat_name] = cat_totals.get(cat_name, 0.0) + float(r.amount)

    category_breakdown = []
    for name, amount in sorted(cat_totals.items(), key=lambda x: -x[1]):
        pct = round((amount / total_spent * 100) if total_spent else 0.0, 1)
        category_breakdown.append({"name": name, "amount": round(amount, 2), "pct_of_total": pct})

    # --- top single expense ---
    expense_rows = [r for r in rows if r.expense_type == "EXPENSE"]
    top_expense = None
    if expense_rows:
        top_row = max(expense_rows, key=lambda r: float(r.amount))
        cat_name = "Uncategorised"
        if top_row.category_id:
            cat = db.session.get(Category, top_row.category_id)
            if cat:
                cat_name = cat.name
        top_expense = {
            "id": top_row.id,
            "amount": float(top_row.amount),
            "currency": top_row.currency,
            "notes": top_row.notes,
            "category": cat_name,
            "spent_at": top_row.spent_at.isoformat(),
        }

    # --- week-over-week change ---
    prev_rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_start,
            Expense.spent_at <= prev_end,
            Expense.expense_type == "EXPENSE",
        )
        .all()
    )
    prev_total = sum(float(r.amount) for r in prev_rows)
    if prev_total == 0:
        wow_change = 0.0
    else:
        wow_change = round((total_spent - prev_total) / prev_total * 100, 1)

    # --- upcoming bills (next 7 days from end of week) ---
    look_ahead_end = end + timedelta(days=7)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.next_due_date >= end,
            Bill.next_due_date <= look_ahead_end,
            Bill.active == True,  # noqa: E712
        )
        .order_by(Bill.next_due_date)
        .limit(5)
        .all()
    )
    upcoming_bills = [
        {"name": b.name, "due_date": b.next_due_date.isoformat(), "amount": float(b.amount)}
        for b in bills
    ]

    # --- auto-generated insights ---
    insights = []
    if wow_change > 20:
        insights.append(
            f"Spending is up {wow_change:.0f}% compared to last week — consider reviewing discretionary expenses."
        )
    elif wow_change < -20:
        insights.append(f"Great job! Spending dropped {abs(wow_change):.0f}% compared to last week.")

    if category_breakdown:
        top_cat = category_breakdown[0]
        if top_cat["pct_of_total"] > 50:
            insights.append(
                f"{top_cat['name']} accounts for over {top_cat['pct_of_total']}% of your spending this week."
            )

    if total_income == 0 and total_spent > 0:
        insights.append("No income recorded this week — make sure all income entries are logged.")

    if net < 0:
        insights.append(f"You spent more than you earned this week by {abs(net):.2f}.")

    if upcoming_bills:
        names = ", ".join(b["name"] for b in upcoming_bills[:3])
        insights.append(f"Upcoming bills due soon: {names}.")

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_spent": round(total_spent, 2),
        "total_income": round(total_income, 2),
        "net": round(net, 2),
        "category_breakdown": category_breakdown,
        "top_expense": top_expense,
        "week_over_week_change": wow_change,
        "upcoming_bills": upcoming_bills,
        "insights": insights,
    }
