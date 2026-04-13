from datetime import date, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Category
import logging

bp = Blueprint("spending_split", __name__)
logger = logging.getLogger("finmind.spending_split")

# Categories classified as essential spending
ESSENTIAL_KEYWORDS = {
    "rent", "mortgage", "utilities", "electricity", "water", "gas",
    "groceries", "grocery", "insurance", "healthcare", "health",
    "medical", "pharmacy", "medicine", "housing", "internet",
    "phone", "transport", "transportation", "fuel", "petrol",
    "childcare", "education", "loan", "debt",
}

# Categories classified as discretionary spending
DISCRETIONARY_KEYWORDS = {
    "dining", "restaurant", "food delivery", "entertainment",
    "movies", "streaming", "shopping", "clothing", "clothes",
    "fashion", "hobby", "hobbies", "travel", "vacation",
    "gaming", "subscription", "gym", "fitness", "beauty",
    "salon", "spa", "coffee", "alcohol", "bar", "gifts",
    "electronics", "gadgets",
}


def _classify_category(name):
    """Classify a category name as essential or discretionary."""
    lower_name = (name or "").lower().strip()
    for keyword in ESSENTIAL_KEYWORDS:
        if keyword in lower_name:
            return "essential"
    for keyword in DISCRETIONARY_KEYWORDS:
        if keyword in lower_name:
            return "discretionary"
    # Default: uncategorized expenses go to discretionary
    return "discretionary"


@bp.get("")
@jwt_required()
def get_spending_split():
    uid = int(get_jwt_identity())

    # Determine date range
    days = int(request.args.get("days", "30"))
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # Get expenses grouped by category
    rows = (
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
        )
        .group_by(Expense.category_id)
        .all()
    )

    # Load category names
    cat_ids = {row.category_id for row in rows if row.category_id}
    categories_map = {}
    if cat_ids:
        cats = db.session.query(Category).filter(Category.id.in_(cat_ids)).all()
        categories_map = {c.id: c.name for c in cats}

    essential_total = 0.0
    discretionary_total = 0.0
    categories = []

    for row in rows:
        cat_id = row.category_id
        cat_name = categories_map.get(cat_id, "Uncategorized")
        amount = float(row.total)
        classification = _classify_category(cat_name)

        if classification == "essential":
            essential_total += amount
        else:
            discretionary_total += amount

        categories.append({
            "category_id": cat_id,
            "category_name": cat_name,
            "total": round(amount, 2),
            "transaction_count": row.count,
            "classification": classification,
        })

    grand_total = essential_total + discretionary_total
    ratio = (
        round(essential_total / discretionary_total, 2)
        if discretionary_total > 0
        else None
    )

    logger.info(
        "Spending split served user=%s essential=%.2f discretionary=%.2f",
        uid, essential_total, discretionary_total,
    )

    return jsonify({
        "essential_total": round(essential_total, 2),
        "discretionary_total": round(discretionary_total, 2),
        "total": round(grand_total, 2),
        "ratio": ratio,
        "essential_pct": (
            round((essential_total / grand_total) * 100, 1)
            if grand_total > 0
            else 0.0
        ),
        "discretionary_pct": (
            round((discretionary_total / grand_total) * 100, 1)
            if grand_total > 0
            else 0.0
        ),
        "categories": categories,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days,
        },
    })
