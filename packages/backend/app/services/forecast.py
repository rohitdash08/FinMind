"""Advanced cash flow forecasting service."""

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Bill


def forecast_cashflow(user_id, months=3):
    """Generate cash flow forecast based on historical spending patterns."""
    today = date.today()
    
    # Get last 90 days of spending
    ninety_ago = today - timedelta(days=90)
    expenses = db.session.query(Expense).filter(
        Expense.user_id == user_id, Expense.spent_at >= ninety_ago
    ).all()
    
    if not expenses:
        return {"forecast": [], "avg_daily_spend": 0, "avg_daily_income": 0, "message": "Not enough data for forecast"}
    
    # Calculate averages
    days_range = max((today - ninety_ago).days, 1)
    total_expense = sum(float(e.amount) for e in expenses if e.expense_type == "EXPENSE")
    total_income = sum(float(e.amount) for e in expenses if e.expense_type == "INCOME")
    
    avg_daily_expense = total_expense / days_range
    avg_daily_income = total_income / days_range
    avg_daily_net = avg_daily_income - avg_daily_expense
    
    # Get upcoming bills
    upcoming_bills = db.session.query(Bill).filter(
        Bill.user_id == user_id, Bill.active == True,
        Bill.next_due_date >= today, Bill.next_due_date <= today + timedelta(days=90)
    ).all()
    
    # Build monthly forecast
    forecast = []
    for m in range(months):
        month_start = today + timedelta(days=30 * m)
        month_end = month_start + timedelta(days=30)
        days_in_month = 30
        
        projected_expense = round(avg_daily_expense * days_in_month, 2)
        projected_income = round(avg_daily_income * days_in_month, 2)
        
        # Add known bills
        bills_total = sum(
            float(b.amount) for b in upcoming_bills
            if month_start <= b.next_due_date <= month_end
        )
        
        projected_expense += bills_total
        net_flow = round(projected_income - projected_expense, 2)
        
        forecast.append({
            "month": m + 1,
            "period": f"{month_start.isoformat()} to {month_end.isoformat()}",
            "projected_income": projected_income,
            "projected_expenses": round(projected_expense, 2),
            "known_bills": round(bills_total, 2),
            "net_flow": net_flow,
            "cumulative_net": round(net_flow * (m + 1), 2),
        })
    
    return {
        "forecast": forecast,
        "avg_daily_spend": round(avg_daily_expense, 2),
        "avg_daily_income": round(avg_daily_income, 2),
        "avg_daily_net": round(avg_daily_net, 2),
        "data_period_days": days_range,
        "upcoming_bills_count": len(upcoming_bills),
    }
