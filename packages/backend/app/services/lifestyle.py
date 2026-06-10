from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy import func
from ..models import Expense, Category
from ..extensions import db


def detect_lifestyle_inflation(user_id: int):
    """
    Detect lifestyle inflation by comparing the last 90 days of spending
    against the 90 days before that.
    """
    today = date.today()
    # Define periods
    period_1_end = today
    period_1_start = today - relativedelta(days=90)
    
    period_2_end = period_1_start
    period_2_start = period_2_end - relativedelta(days=90)

    # Helper to get category spending for a period
    def get_spending(start_d, end_d):
        result = (
            db.session.query(
                Category.name,
                func.sum(Expense.amount).label("total")
            )
            .join(Expense, Expense.category_id == Category.id)
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= start_d,
                Expense.spent_at < end_d,
                Expense.expense_type == "EXPENSE"
            )
            .group_by(Category.name)
            .all()
        )
        return {row.name: float(row.total) for row in result}

    recent_spending = get_spending(period_1_start, period_1_end)
    past_spending = get_spending(period_2_start, period_2_end)

    total_recent = sum(recent_spending.values())
    total_past = sum(past_spending.values())

    inflation_detected = False
    overall_increase_pct = 0.0

    if total_past > 0:
        overall_increase_pct = ((total_recent - total_past) / total_past) * 100
        # If overall spending increased by more than 10%, flag as potential inflation
        if overall_increase_pct > 10.0:
            inflation_detected = True

    # Identify top categories driving the inflation
    drivers = []
    for cat, recent_amt in recent_spending.items():
        past_amt = past_spending.get(cat, 0.0)
        # Category must have meaningful amount
        if recent_amt > past_amt and recent_amt > 50:
            increase = recent_amt - past_amt
            pct = ((increase) / past_amt * 100) if past_amt > 0 else 100.0
            if pct > 15.0:
                drivers.append({
                    "category": cat,
                    "past_amount": past_amt,
                    "recent_amount": recent_amt,
                    "increase_percentage": round(pct, 2)
                })
    
    # Sort drivers by absolute increase
    drivers.sort(key=lambda x: x["recent_amount"] - x["past_amount"], reverse=True)

    return {
        "inflation_detected": inflation_detected and len(drivers) > 0,
        "overall_increase_percentage": round(overall_increase_pct, 2),
        "recent_total": total_recent,
        "past_total": total_past,
        "period_days": 90,
        "driving_categories": drivers[:5]  # Top 5 drivers
    }
