from datetime import date, timedelta
from collections import defaultdict

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Category
import logging

bp = Blueprint("budget_suggest", __name__)
logger = logging.getLogger("finmind.budget_suggest")

# 50/30/20 rule allocation percentages
NEEDS_PCT = 0.50
WANTS_PCT = 0.30
SAVINGS_PCT = 0.20


@bp.get("")
@jwt_required()
def get_budget_suggestions():
    uid = int(get_jwt_identity())

    # Look at last 90 days of spending
    end_date = date.today()
    start_date = end_date - timedelta(days=90)

    # Get all expenses in the period
    expenses = (
        db.session.query(
            Expense.category_id,
            Expense.expense_type,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
        )
        .group_by(Expense.category_id, Expense.expense_type)
        .all()
    )

    # Calculate totals
    total_expense = 0.0
    total_income = 0.0
    spending_by_category = defaultdict(float)

    for row in expenses:
        amount = float(row.total)
        if row.expense_type == "INCOME":
            total_income += amount
        else:
            total_expense += amount
            spending_by_category[row.category_id] += amount

    # Monthly averages (90 days ~ 3 months)
    monthly_expense = round(total_expense / 3, 2)
    monthly_income = round(total_income / 3, 2) if total_income > 0 else 0.0

    # If no income data, estimate from spending (assume spending = 80% of income)
    estimated_income = monthly_income if monthly_income > 0 else round(monthly_expense / 0.8, 2)

    # 50/30/20 budget targets
    needs_budget = round(estimated_income * NEEDS_PCT, 2)
    wants_budget = round(estimated_income * WANTS_PCT, 2)
    savings_target = round(estimated_income * SAVINGS_PCT, 2)

    # Load category names
    cat_ids = {cid for cid in spending_by_category if cid is not None}
    categories_map = {}
    if cat_ids:
        cats = db.session.query(Category).filter(Category.id.in_(cat_ids)).all()
        categories_map = {c.id: c.name for c in cats}

    # Build per-category suggestions
    suggestions = []
    for cat_id, total in spending_by_category.items():
        cat_name = categories_map.get(cat_id, "Uncategorized")
        monthly_avg = round(float(total) / 3, 2)
        # Suggest budget as monthly average + 10% buffer
        suggested = round(monthly_avg * 1.10, 2)

        suggestion = {
            "category_id": cat_id,
            "category_name": cat_name,
            "monthly_average": monthly_avg,
            "suggested_budget": suggested,
            "period_total": round(float(total), 2),
        }

        # Add advice
        if monthly_expense > 0:
            pct_of_total = (monthly_avg / monthly_expense) * 100
            suggestion["pct_of_spending"] = round(pct_of_total, 1)

        suggestions.append(suggestion)

    # Sort by suggested_budget descending
    suggestions.sort(key=lambda s: s["suggested_budget"], reverse=True)

    logger.info("Budget suggestions served user=%s categories=%s", uid, len(suggestions))

    return jsonify({
        "suggestions": suggestions,
        "monthly_income": monthly_income,
        "estimated_monthly_income": estimated_income,
        "monthly_expense": monthly_expense,
        "savings_target": savings_target,
        "budget_rule": {
            "needs": needs_budget,
            "wants": wants_budget,
            "savings": savings_target,
        },
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": 90,
        },
    })
