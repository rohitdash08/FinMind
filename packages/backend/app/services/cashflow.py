import logging
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal
from typing import Optional

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Bill, Expense, RecurringExpense

logger = logging.getLogger("finmind.cashflow")


def _days_in_month(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def _add_months(d: date, n: int) -> date:
    """Add n months to a date, clamping day to end of month."""
    year = d.year
    month = d.month + n
    while month > 12:
        month -= 12
        year += 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _get_monthly_actual(uid: int, year: int, month: int) -> dict:
    """Get actual income and expense totals for a past month."""
    income = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.user_id == uid,
        extract("year", Expense.spent_at) == year,
        extract("month", Expense.spent_at) == month,
        Expense.expense_type == "INCOME",
    ).scalar()

    expenses = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.user_id == uid,
        extract("year", Expense.spent_at) == year,
        extract("month", Expense.spent_at) == month,
        Expense.expense_type != "INCOME",
    ).scalar()

    return {"income": float(income or 0), "expenses": float(expenses or 0)}


def _calculate_trend(values: list[float]) -> float:
    """Calculate linear trend slope using least squares."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


def _confidence_from_data_points(n: int) -> str:
    """Return confidence label based on historical data points."""
    if n >= 6:
        return "high"
    elif n >= 3:
        return "medium"
    return "low"


def _get_recurring_monthly(uid: int, target_month: date) -> float:
    """Sum up recurring expenses that will trigger in target_month."""
    today = date.today()
    actives = db.session.query(RecurringExpense).filter(
        RecurringExpense.user_id == uid,
        RecurringExpense.active == True,
        RecurringExpense.expense_type != "INCOME",
    ).all()

    total = 0.0
    for rec in actives:
        start = rec.start_date
        end = rec.end_date or date(9999, 12, 31)
        if end < target_month:
            continue
        cadence = rec.cadence.value if hasattr(rec.cadence, "value") else str(rec.cadence)
        amount = float(rec.amount)
        if cadence == "MONTHLY":
            total += amount
        elif cadence == "WEEKLY":
            total += amount * 4.33  # avg weeks per month
        elif cadence == "DAILY":
            total += amount * _days_in_month(target_month.year, target_month.month)
        elif cadence == "YEARLY":
            if rec.start_date.month == target_month.month:
                total += amount
    return total


def _get_upcoming_bills(uid: int, target_month: date) -> float:
    """Sum bills due in target_month."""
    month_start = date(target_month.year, target_month.month, 1)
    month_end = date(target_month.year, target_month.month,
                     _days_in_month(target_month.year, target_month.month))

    bills = db.session.query(Bill).filter(
        Bill.user_id == uid,
        Bill.active == True,
        Bill.next_due_date >= month_start,
        Bill.next_due_date <= month_end,
    ).all()

    total = sum(float(b.amount) for b in bills)
    return total


def forecast_cash_flow(uid: int, months_ahead: int = 3) -> dict:
    """
    Forecast cash flow for the next N months.

    Uses:
    - Historical income/expense trend (up to 6 months back)
    - Recurring expense schedule
    - Upcoming bills

    Returns:
        {
            "months": [
                {
                    "month": "2026-05",
                    "projected_income": 50000.0,
                    "projected_expenses": 35000.0,
                    "projected_net": 15000.0,
                    "scheduled_recurring": 12000.0,
                    "scheduled_bills": 5000.0,
                    "confidence": "high",
                    "anomaly": false
                }
            ],
            "summary": {
                "avg_monthly_surplus": 12000.0,
                "trend": "improving" | "declining" | "stable",
                "data_quality": "high" | "medium" | "low"
            }
        }
    """
    months_ahead = max(1, min(months_ahead, 12))

    # Gather historical data (up to 6 months back)
    today = date.today()
    historical = []
    for i in range(1, 7):
        ref = _add_months(today, -i)
        actual = _get_monthly_actual(uid, ref.year, ref.month)
        if actual["income"] > 0 or actual["expenses"] > 0:
            historical.append(actual)

    historical.reverse()  # Chronological order

    # Calculate trends
    incomes = [h["income"] for h in historical]
    expenses = [h["expenses"] for h in historical]

    avg_income = sum(incomes) / len(incomes) if incomes else 0.0
    avg_expenses = sum(expenses) / len(expenses) if expenses else 0.0
    income_trend = _calculate_trend(incomes) if len(incomes) >= 2 else 0.0
    expense_trend = _calculate_trend(expenses) if len(expenses) >= 2 else 0.0

    confidence_label = _confidence_from_data_points(len(historical))

    # Determine overall trend
    net_values = [h["income"] - h["expenses"] for h in historical]
    net_trend = _calculate_trend(net_values) if len(net_values) >= 2 else 0.0
    if net_trend > 500:
        trend_label = "improving"
    elif net_trend < -500:
        trend_label = "declining"
    else:
        trend_label = "stable"

    # Generate forecasts
    forecast_months = []
    for i in range(1, months_ahead + 1):
        target = _add_months(today, i)
        target_first = date(target.year, target.month, 1)

        # Apply trend to average
        proj_income = max(0, avg_income + income_trend * i)
        proj_expenses_base = max(0, avg_expenses + expense_trend * i)

        # Add scheduled amounts
        scheduled_recurring = _get_recurring_monthly(uid, target_first)
        scheduled_bills = _get_upcoming_bills(uid, target_first)

        # Combined projected expenses (max of trend or scheduled)
        proj_expenses = max(proj_expenses_base, scheduled_recurring + scheduled_bills)

        proj_net = proj_income - proj_expenses

        # Anomaly detection: net < -20% of avg income
        anomaly = avg_income > 0 and proj_net < -(avg_income * 0.2)

        forecast_months.append({
            "month": f"{target.year:04d}-{target.month:02d}",
            "projected_income": round(proj_income, 2),
            "projected_expenses": round(proj_expenses, 2),
            "projected_net": round(proj_net, 2),
            "scheduled_recurring": round(scheduled_recurring, 2),
            "scheduled_bills": round(scheduled_bills, 2),
            "confidence": confidence_label,
            "anomaly": anomaly,
        })

    avg_surplus = sum(m["projected_net"] for m in forecast_months) / len(forecast_months) if forecast_months else 0.0

    logger.info(
        "Cash flow forecast uid=%s months=%s confidence=%s trend=%s",
        uid, months_ahead, confidence_label, trend_label
    )

    return {
        "months": forecast_months,
        "summary": {
            "avg_monthly_surplus": round(avg_surplus, 2),
            "trend": trend_label,
            "data_quality": confidence_label,
            "historical_months_used": len(historical),
        },
    }

