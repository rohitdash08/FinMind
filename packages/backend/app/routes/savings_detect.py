"""Savings opportunity detection engine."""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category, RecurringExpense
from datetime import date, timedelta
bp = Blueprint("savings_detect", __name__)

@bp.get("")
@jwt_required()
def detect():
    uid = int(get_jwt_identity())
    today = date.today()
    thirty = today - timedelta(days=30)
    opportunities = []

    # 1. Recurring expenses that could be reduced
    recurring = db.session.query(RecurringExpense).filter_by(user_id=uid, active=True).all()
    for r in recurring:
        if float(r.amount) > 50:
            opportunities.append({"type": "recurring_review", "amount": float(r.amount), "cadence": r.cadence.value if r.cadence else "unknown", "description": r.notes, "suggestion": f"Review recurring charge of {float(r.amount):.2f} ({r.notes}). Can you negotiate a lower rate?"})

    # 2. Categories with high spending that could be cut
    cats = db.session.query(func.coalesce(Category.name, "Uncategorized").label("cat"), func.sum(Expense.amount).label("total")).outerjoin(Category, Expense.category_id == Category.id).filter(Expense.user_id == uid, Expense.spent_at >= thirty, Expense.expense_type == "EXPENSE").group_by(Category.name).order_by(func.sum(Expense.amount).desc()).all()
    
    total = sum(float(c.total) for c in cats)
    for c in cats[:3]:
        amt = float(c.total)
        pct = (amt / total * 100) if total else 0
        if pct > 25:
            save = round(amt * 0.1, 2)
            opportunities.append({"type": "high_spending_category", "category": c.cat, "amount": amt, "percentage": round(pct, 1), "potential_savings": save, "suggestion": f"Cutting {c.cat} by 10% could save {save:.2f}/month"})

    # 3. Small frequent transactions
    small_freq = db.session.query(func.count(Expense.id).label("cnt"), func.sum(Expense.amount).label("total")).filter(Expense.user_id == uid, Expense.spent_at >= thirty, Expense.amount <= 10, Expense.expense_type == "EXPENSE").first()
    if small_freq and small_freq.cnt and small_freq.cnt > 10:
        opportunities.append({"type": "small_purchases", "count": small_freq.cnt, "total": float(small_freq.total or 0), "suggestion": f"{small_freq.cnt} small purchases (<10) totaling {float(small_freq.total or 0):.2f}. These add up!"})

    total_potential = sum(o.get("potential_savings", 0) for o in opportunities)
    return jsonify(opportunities=opportunities, total_potential_savings=round(total_potential, 2), opportunity_count=len(opportunities))
