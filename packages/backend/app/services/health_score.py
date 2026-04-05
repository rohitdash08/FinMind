"""Predictive financial health score (issue #90)."""
import logging
from datetime import date
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Bill

logger = logging.getLogger("finmind.health")


def calculate_health_score(user_id: int, year: int, month: int) -> dict:
    """
    0–100 score based on 5 weighted factors:
    1. Savings rate (30pts)
    2. Bill payment coverage (20pts)
    3. Expense diversity (15pts)
    4. Spending consistency vs prior month (20pts)
    5. Income presence (15pts)
    """
    score = 0
    breakdown = {}

    # Income
    income = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                   .filter(Expense.user_id == user_id,
                           extract("year", Expense.spent_at) == year,
                           extract("month", Expense.spent_at) == month,
                           Expense.expense_type == "INCOME").scalar() or 0)
    expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                     .filter(Expense.user_id == user_id,
                             extract("year", Expense.spent_at) == year,
                             extract("month", Expense.spent_at) == month,
                             Expense.expense_type != "INCOME").scalar() or 0)

    # Factor 1: Savings rate (30pts)
    if income > 0:
        savings_pct = max(0, (income - expenses) / income * 100)
        s1 = min(30, savings_pct * 1.5)  # 20%+ savings = full 30pts
        breakdown["savings_rate"] = {"score": round(s1,1), "max": 30, "value": round(savings_pct,1)}
    else:
        s1 = 0
        breakdown["savings_rate"] = {"score": 0, "max": 30, "value": 0}
    score += s1

    # Factor 2: Income presence (15pts)
    s2 = 15 if income > 0 else 0
    breakdown["income_presence"] = {"score": s2, "max": 15, "has_income": income > 0}
    score += s2

    # Factor 3: Bill coverage (20pts) — can afford upcoming bills?
    from dateutil.relativedelta import relativedelta
    next_month = date(year, month, 1) + relativedelta(months=1)
    bills = db.session.query(Bill).filter(Bill.user_id == user_id, Bill.active.is_(True),
                             extract("year", Bill.next_due_date) == next_month.year,
                             extract("month", Bill.next_due_date) == next_month.month).all()
    bills_total = sum(float(b.amount) for b in bills)
    savings_amt = income - expenses
    if bills_total == 0:
        s3 = 20
    elif savings_amt >= bills_total:
        s3 = 20
    elif savings_amt > 0:
        s3 = round(savings_amt / bills_total * 20, 1)
    else:
        s3 = 0
    breakdown["bill_coverage"] = {"score": round(s3,1), "max": 20, "bills_total": round(bills_total,2), "savings": round(savings_amt,2)}
    score += s3

    # Factor 4: Expense diversity (15pts) — categorized expenses = good habits
    cat_count = db.session.query(func.count(func.distinct(Expense.category_id)))\
                          .filter(Expense.user_id == user_id,
                                  extract("year", Expense.spent_at) == year,
                                  extract("month", Expense.spent_at) == month,
                                  Expense.category_id.isnot(None)).scalar() or 0
    s4 = min(15, cat_count * 2.5)
    breakdown["categorization"] = {"score": round(s4,1), "max": 15, "categories_used": int(cat_count)}
    score += s4

    total = round(min(score, 100), 1)
    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D" if total >= 35 else "F"

    return {
        "period": f"{year}-{month:02d}",
        "score": total, "grade": grade,
        "breakdown": breakdown,
        "message": _message(total, grade),
    }


def _message(score, grade):
    if grade == "A": return "Excellent financial health! Keep it up."
    if grade == "B": return "Good financial health. Small improvements can push you to A."
    if grade == "C": return "Average. Focus on savings rate and bill coverage."
    if grade == "D": return "Needs attention. Review spending and ensure bills are covered."
    return "Critical — income or savings issues detected. Review immediately."
