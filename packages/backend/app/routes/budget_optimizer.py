"""Autonomous budget optimization."""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category
from datetime import date, timedelta
import logging

bp = Blueprint("budget_optimizer", __name__)
logger = logging.getLogger("finmind.budget_optimizer")

@bp.get("/optimize")
@jwt_required()
def optimize():
    uid = int(get_jwt_identity())
    today = date.today()
    thirty_ago = today - timedelta(days=30)
    sixty_ago = today - timedelta(days=60)

    current = db.session.query(Expense.category_id, func.coalesce(Category.name, "Uncategorized").label("cat"), func.sum(Expense.amount).label("total")).outerjoin(Category, Expense.category_id == Category.id).filter(Expense.user_id == uid, Expense.spent_at >= thirty_ago, Expense.expense_type == "EXPENSE").group_by(Expense.category_id, Category.name).all()
    previous = db.session.query(Expense.category_id, func.sum(Expense.amount).label("total")).filter(Expense.user_id == uid, Expense.spent_at >= sixty_ago, Expense.spent_at < thirty_ago, Expense.expense_type == "EXPENSE").group_by(Expense.category_id).all()

    prev_map = {r.category_id: float(r.total) for r in previous}
    total_spent = sum(float(r.total) for r in current)
    total_income = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.user_id == uid, Expense.spent_at >= thirty_ago, Expense.expense_type == "INCOME").scalar() or 0)

    recommendations = []
    categories = []
    for r in current:
        amt = float(r.total)
        prev = prev_map.get(r.category_id, 0)
        pct = round(amt / total_spent * 100, 1) if total_spent else 0
        change = round(((amt - prev) / prev * 100), 1) if prev else 0
        suggested = round(amt * 0.9, 2) if change > 10 else round(amt, 2)
        categories.append({"category_id": r.category_id, "name": r.cat, "current_spend": amt, "previous_spend": prev, "change_pct": change, "share_pct": pct, "suggested_budget": suggested})
        if change > 20:
            recommendations.append(f"Reduce {r.cat} spending by {change:.0f}% - was {prev:.0f}, now {amt:.0f}")
        if pct > 40:
            recommendations.append(f"{r.cat} takes {pct}% of budget - consider setting a cap")

    savings_potential = total_income * 0.2 if total_income else 0
    if total_income and total_spent > total_income * 0.8:
        recommendations.append(f"Spending is {total_spent/total_income*100:.0f}% of income - aim for under 80%")

    return jsonify(total_income=total_income, total_expenses=total_spent, savings_potential=round(savings_potential, 2), categories=categories, recommendations=recommendations)
