"""Cash flow forecast engine (issue #70)."""
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Bill, RecurringExpense

logger = logging.getLogger("finmind.cashflow_engine")


def _daily_average(user_id: int, days: int, expense_type: str) -> float:
    start = date.today() - timedelta(days=days)
    total = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                  .filter(Expense.user_id == user_id, Expense.spent_at >= start,
                          Expense.expense_type == expense_type).scalar() or 0)
    return total / days if days else 0


def daily_forecast(user_id: int, days_ahead: int = 30) -> dict:
    """Day-by-day cash flow forecast with known bills overlaid."""
    daily_income = _daily_average(user_id, 90, "INCOME")
    daily_expense = _daily_average(user_id, 90, "EXPENSE")

    # Map bills to their due dates
    bills = (db.session.query(Bill)
             .filter(Bill.user_id == user_id, Bill.active.is_(True)).all())
    bill_map = {}
    for b in bills:
        if b.next_due_date:
            bill_map[b.next_due_date] = bill_map.get(b.next_due_date, 0) + float(b.amount)

    today = date.today()
    days = []
    running = 0.0

    for i in range(days_ahead):
        d = today + timedelta(days=i)
        known_bill = bill_map.get(d, 0)
        projected_income = round(daily_income, 2)
        projected_expense = round(daily_expense + known_bill, 2)
        net = round(projected_income - projected_expense, 2)
        running = round(running + net, 2)
        days.append({
            "date": d.isoformat(),
            "projected_income": projected_income,
            "projected_expense": projected_expense,
            "known_bill": round(known_bill, 2),
            "net": net,
            "cumulative": running,
        })

    negative_days = [d for d in days if d["net"] < 0]
    return {
        "days_ahead": days_ahead,
        "daily_avg_income": round(daily_income, 2),
        "daily_avg_expense": round(daily_expense, 2),
        "forecast": days,
        "negative_flow_days": len(negative_days),
        "lowest_point": round(min(d["cumulative"] for d in days), 2) if days else 0,
        "summary": f"{len(negative_days)} negative cash flow day(s) in next {days_ahead} days.",
    }
