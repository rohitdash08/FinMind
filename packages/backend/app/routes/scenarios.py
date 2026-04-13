"""Financial scenario simulator (what-if planning)."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Expense
from datetime import date, timedelta
import logging

bp = Blueprint("scenarios", __name__)
logger = logging.getLogger("finmind.scenarios")

@bp.post("/simulate")
@jwt_required()
def simulate():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    months = min(int(data.get("months", 6)), 24)
    income_change_pct = float(data.get("income_change_pct", 0))
    expense_change_pct = float(data.get("expense_change_pct", 0))
    one_time_expense = float(data.get("one_time_expense", 0))
    one_time_income = float(data.get("one_time_income", 0))
    savings_rate = float(data.get("savings_rate", 0)) / 100

    today = date.today()
    ninety_ago = today - timedelta(days=90)
    expenses = db.session.query(Expense).filter(Expense.user_id == uid, Expense.spent_at >= ninety_ago).all()
    
    total_exp = sum(float(e.amount) for e in expenses if e.expense_type == "EXPENSE")
    total_inc = sum(float(e.amount) for e in expenses if e.expense_type == "INCOME")
    days = max((today - ninety_ago).days, 1)
    monthly_exp = (total_exp / days) * 30
    monthly_inc = (total_inc / days) * 30

    adj_income = monthly_inc * (1 + income_change_pct / 100)
    adj_expense = monthly_exp * (1 + expense_change_pct / 100)

    projection = []
    cumulative_savings = 0
    for m in range(1, months + 1):
        inc = adj_income + (one_time_income if m == 1 else 0)
        exp = adj_expense + (one_time_expense if m == 1 else 0)
        savings = (inc - exp) * (1 - savings_rate) if savings_rate else inc - exp
        cumulative_savings += savings
        projection.append({"month": m, "income": round(inc, 2), "expenses": round(exp, 2), "net": round(savings, 2), "cumulative": round(cumulative_savings, 2)})

    return jsonify(
        baseline={"monthly_income": round(monthly_inc, 2), "monthly_expenses": round(monthly_exp, 2)},
        adjustments={"income_change_pct": income_change_pct, "expense_change_pct": expense_change_pct},
        projection=projection,
        summary={"total_saved": round(cumulative_savings, 2), "months": months}
    )
