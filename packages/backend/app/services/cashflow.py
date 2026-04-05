"""Advanced cash flow forecasting (issue #93)."""
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Bill, RecurringExpense

logger = logging.getLogger("finmind.cashflow")


def _avg_monthly(user_id: int, months: int, expense_type: str) -> float:
    ref = date.today()
    start = ref - relativedelta(months=months)
    total = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                  .filter(Expense.user_id == user_id, Expense.spent_at >= start,
                          Expense.expense_type == expense_type).scalar() or 0)
    return total / months


def forecast(user_id: int, months_ahead: int = 3, history_months: int = 3) -> dict:
    """
    Project cash flow for the next N months using:
    - Historical average income/expenses
    - Known upcoming bills
    - Active recurring expenses
    """
    avg_income = _avg_monthly(user_id, history_months, "INCOME")
    avg_expense = _avg_monthly(user_id, history_months, "EXPENSE")

    active_recurring = (db.session.query(RecurringExpense)
                        .filter(RecurringExpense.user_id == user_id,
                                RecurringExpense.active.is_(True)).all())
    monthly_recurring = sum(
        float(r.amount) for r in active_recurring
        if r.cadence.value in ("MONTHLY", "WEEKLY")
    )

    today = date.today()
    projections = []
    running_balance = 0.0

    for i in range(1, months_ahead + 1):
        proj_date = today + relativedelta(months=i)
        y, m = proj_date.year, proj_date.month

        # Known bills due this month
        bills = (db.session.query(Bill)
                 .filter(Bill.user_id == user_id, Bill.active.is_(True),
                         extract("year", Bill.next_due_date) == y,
                         extract("month", Bill.next_due_date) == m).all())
        bills_total = sum(float(b.amount) for b in bills)

        projected_income = round(avg_income, 2)
        projected_expenses = round(avg_expense + bills_total, 2)
        net = round(projected_income - projected_expenses, 2)
        running_balance = round(running_balance + net, 2)

        projections.append({
            "month": f"{y}-{m:02d}",
            "projected_income": projected_income,
            "projected_expenses": projected_expenses,
            "known_bills": round(bills_total, 2),
            "net": net,
            "running_balance": running_balance,
            "risk": "high" if net < 0 else "medium" if net < avg_income * 0.1 else "low",
        })

    return {
        "history_months": history_months,
        "avg_monthly_income": round(avg_income, 2),
        "avg_monthly_expenses": round(avg_expense, 2),
        "projections": projections,
        "summary": f"{'Positive' if running_balance >= 0 else 'Negative'} cash flow over {months_ahead} months. Net: ${running_balance:.2f}",
    }
