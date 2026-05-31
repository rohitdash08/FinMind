import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.lifestyle_inflation")


def _monthly_breakdown(uid: int, months: int = 12) -> list[dict[str, Any]]:
    today = date.today()
    rows = []
    for i in range(months - 1, -1, -1):
        d = today.replace(day=1) - timedelta(days=30 * i)
        ym = d.strftime("%Y-%m")
        year, month = d.year, d.month
        income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.expense_type == "INCOME",
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
            )
            .scalar()
        )
        expenses = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.expense_type != "INCOME",
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
            )
            .scalar()
        )
        discretionary = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.expense_type != "INCOME",
                Expense.category_id.is_(None),
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
            )
            .scalar()
        )
        rows.append({
            "month": ym,
            "income": float(income or 0),
            "expenses": float(expenses or 0),
            "discretionary": float(discretionary or 0),
        })
    return rows


def detect_lifestyle_creep(uid: int, months: int = 12) -> dict[str, Any]:
    breakdown = _monthly_breakdown(uid, months)
    if len(breakdown) < 3:
        return {"trend": "insufficient_data", "months": breakdown, "insights": []}

    insights: list[str] = []
    first_half = breakdown[: len(breakdown) // 2]
    second_half = breakdown[len(breakdown) // 2 :]

    avg_expense_first = sum(m["expenses"] for m in first_half) / len(first_half)
    avg_expense_second = sum(m["expenses"] for m in second_half) / len(second_half)
    expense_growth_pct = ((avg_expense_second - avg_expense_first) / avg_expense_first * 100) if avg_expense_first > 0 else 0

    avg_discretionary_first = sum(m["discretionary"] for m in first_half) / len(first_half)
    avg_discretionary_second = sum(m["discretionary"] for m in second_half) / len(second_half)
    discretionary_growth_pct = ((avg_discretionary_second - avg_discretionary_first) / avg_discretionary_first * 100) if avg_discretionary_first > 0 else 0

    avg_income_first = sum(m["income"] for m in first_half) / len(first_half)
    avg_income_second = sum(m["income"] for m in second_half) / len(second_half)
    income_growth_pct = ((avg_income_second - avg_income_first) / avg_income_first * 100) if avg_income_first > 0 else 0

    if discretionary_growth_pct > 15:
        insights.append(
            f"Discretionary spending grew {discretionary_growth_pct:.0f}% — possible lifestyle creep"
        )
    if expense_growth_pct > income_growth_pct + 10:
        insights.append(
            f"Expenses grew {expense_growth_pct:.0f}% vs income {income_growth_pct:.0f}% — spending outpaces earnings"
        )
    if avg_expense_second / avg_income_second > 0.8 if avg_income_second > 0 else False:
        insights.append("Expense-to-income ratio exceeds 80% — high burn rate")

    trend = "stable"
    if discretionary_growth_pct > 20 or expense_growth_pct > 20:
        trend = "inflation"
    elif discretionary_growth_pct < -10 or expense_growth_pct < -10:
        trend = "deflation"

    return {
        "trend": trend,
        "months_tracked": months,
        "expense_growth_pct": round(expense_growth_pct, 1),
        "discretionary_growth_pct": round(discretionary_growth_pct, 1),
        "income_growth_pct": round(income_growth_pct, 1),
        "expense_to_income_ratio": round(avg_expense_second / avg_income_second * 100, 1) if avg_income_second > 0 else 0,
        "insights": insights,
        "monthly_breakdown": breakdown,
    }
