"""
Lifestyle inflation detection (issue #118).
Detects when spending grows faster than income over time.
"""
import logging
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.inflation")


def _monthly_totals(user_id: int, year: int, months: int = 6) -> list[dict]:
    """Get monthly income + expense totals for last N months."""
    from datetime import date
    from dateutil.relativedelta import relativedelta
    today = date(year, 12, 1) if year < date.today().year else date.today()
    results = []
    for i in range(months - 1, -1, -1):
        ref = today - relativedelta(months=i)
        y, m = ref.year, ref.month
        income = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                       .filter(Expense.user_id == user_id,
                               extract("year", Expense.spent_at) == y,
                               extract("month", Expense.spent_at) == m,
                               Expense.expense_type == "INCOME").scalar() or 0)
        expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                         .filter(Expense.user_id == user_id,
                                 extract("year", Expense.spent_at) == y,
                                 extract("month", Expense.spent_at) == m,
                                 Expense.expense_type != "INCOME").scalar() or 0)
        results.append({"month": f"{y}-{m:02d}", "income": income, "expenses": expenses})
    return results


def detect_lifestyle_inflation(user_id: int, year: int, months: int = 6) -> dict:
    history = _monthly_totals(user_id, year, months)
    if len(history) < 2:
        return {"detected": False, "message": "Not enough data.", "history": history}

    # Compare first half vs second half averages
    mid = len(history) // 2
    first_half = history[:mid]
    second_half = history[mid:]

    avg_exp_first = sum(h["expenses"] for h in first_half) / len(first_half)
    avg_exp_second = sum(h["expenses"] for h in second_half) / len(second_half)
    avg_inc_first = sum(h["income"] for h in first_half) / len(first_half)
    avg_inc_second = sum(h["income"] for h in second_half) / len(second_half)

    exp_growth = ((avg_exp_second - avg_exp_first) / avg_exp_first * 100) if avg_exp_first else 0
    inc_growth = ((avg_inc_second - avg_inc_first) / avg_inc_first * 100) if avg_inc_first else 0

    detected = exp_growth > 10 and exp_growth > inc_growth + 5

    return {
        "detected": detected,
        "expense_growth_pct": round(exp_growth, 1),
        "income_growth_pct": round(inc_growth, 1),
        "message": (
            f"Lifestyle inflation detected: expenses grew {exp_growth:.1f}% vs income {inc_growth:.1f}% over {months} months."
            if detected else
            f"No significant lifestyle inflation. Expense growth: {exp_growth:.1f}%, income growth: {inc_growth:.1f}%."
        ),
        "history": history,
    }
