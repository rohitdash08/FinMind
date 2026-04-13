"""Predictive financial health score."""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Bill
from datetime import date, timedelta
bp = Blueprint("health_score", __name__)

@bp.get("")
@jwt_required()
def get_score():
    uid = int(get_jwt_identity())
    today = date.today()
    thirty = today - timedelta(days=30)

    income = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.user_id == uid, Expense.spent_at >= thirty, Expense.expense_type == "INCOME").scalar() or 0)
    expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.user_id == uid, Expense.spent_at >= thirty, Expense.expense_type == "EXPENSE").scalar() or 0)
    
    score = 50  # base
    factors = []

    # Savings rate (0-25 pts)
    if income > 0:
        savings_rate = (income - expenses) / income
        savings_pts = min(25, max(0, int(savings_rate * 100)))
        score += savings_pts
        factors.append({"name": "Savings Rate", "score": savings_pts, "max": 25, "detail": f"{savings_rate*100:.0f}% of income saved"})
    else:
        factors.append({"name": "Savings Rate", "score": 0, "max": 25, "detail": "No income data"})

    # Expense stability (0-15 pts)
    sixty = today - timedelta(days=60)
    prev_expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.user_id == uid, Expense.spent_at >= sixty, Expense.spent_at < thirty, Expense.expense_type == "EXPENSE").scalar() or 0)
    if prev_expenses > 0:
        volatility = abs(expenses - prev_expenses) / prev_expenses
        stab_pts = max(0, int(15 * (1 - min(volatility, 1))))
        score += stab_pts
        factors.append({"name": "Expense Stability", "score": stab_pts, "max": 15, "detail": f"{volatility*100:.0f}% month-over-month change"})
    else:
        score += 7
        factors.append({"name": "Expense Stability", "score": 7, "max": 15, "detail": "Not enough history"})

    # Bill management (0-10 pts)
    overdue = db.session.query(Bill).filter(Bill.user_id == uid, Bill.active == True, Bill.next_due_date < today).count()
    bill_pts = max(0, 10 - overdue * 3)
    score += bill_pts
    factors.append({"name": "Bill Management", "score": bill_pts, "max": 10, "detail": f"{overdue} overdue bills"})

    score = max(0, min(100, score))
    if score >= 80: grade = "Excellent"
    elif score >= 60: grade = "Good"
    elif score >= 40: grade = "Fair"
    else: grade = "Needs Improvement"

    tips = []
    if income > 0 and (income - expenses) / income < 0.2:
        tips.append("Try to save at least 20% of your income")
    if overdue > 0:
        tips.append(f"Pay {overdue} overdue bill(s) to improve your score")
    if not tips:
        tips.append("Keep up the good work!")

    return jsonify(score=score, grade=grade, factors=factors, tips=tips, income=income, expenses=expenses)
