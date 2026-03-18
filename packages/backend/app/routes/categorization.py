"""
Routes for intelligent transaction categorization.

Endpoints:
  POST   /categorization/expenses/:id/categorize       – auto-categorize one expense
  POST   /categorization/expenses/bulk-categorize      – auto-categorize many expenses
  POST   /categorization/expenses/:id/correct          – record user correction (learning)
  GET    /categorization/rules                         – list user categorization rules
  POST   /categorization/rules                         – create a rule
  DELETE /categorization/rules/:rule_id                – delete a rule
  GET    /categorization/defaults                      – list default category names
"""

import logging
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Category, CategoryRule, Expense
from ..services.categorization import categorize_expense, record_correction

bp = Blueprint("categorization", __name__)
logger = logging.getLogger("finmind.categorization_routes")

DEFAULT_CATEGORIES = [
    "Food",
    "Transport",
    "Entertainment",
    "Bills",
    "Shopping",
    "Health",
    "Education",
    "Income",
    "Transfer",
    "Other",
]


# ---------------------------------------------------------------------------
# Auto-categorize single expense
# ---------------------------------------------------------------------------


@bp.post("/expenses/<int:expense_id>/categorize")
@jwt_required()
def categorize_one(expense_id: int):
    uid = int(get_jwt_identity())
    expense = db.session.get(Expense, expense_id)
    if not expense or expense.user_id != uid:
        return jsonify(error="not found"), 404

    result = categorize_expense(
        user_id=uid,
        description=expense.notes or "",
        amount=Decimal(str(expense.amount)),
    )

    # Apply the suggested category to the expense
    if result["category_id"] is not None:
        expense.category_id = result["category_id"]
        db.session.commit()

    logger.info(
        "Auto-categorized expense id=%s user=%s cat=%s confidence=%s method=%s",
        expense_id,
        uid,
        result.get("category_name"),
        result.get("confidence"),
        result.get("method"),
    )

    return jsonify(
        {
            "expense_id": expense_id,
            "category_id": result["category_id"],
            "category_name": result["category_name"],
            "confidence": result["confidence"],
            "method": result["method"],
        }
    )


# ---------------------------------------------------------------------------
# Bulk categorize
# ---------------------------------------------------------------------------


@bp.post("/expenses/bulk-categorize")
@jwt_required()
def bulk_categorize():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    expense_ids = data.get("expense_ids")

    if expense_ids is not None:
        # Explicit list
        if not isinstance(expense_ids, list):
            return jsonify(error="expense_ids must be a list"), 400
        expenses = (
            db.session.query(Expense)
            .filter(Expense.id.in_(expense_ids), Expense.user_id == uid)
            .all()
        )
    else:
        # Default: all uncategorized expenses for this user
        expenses = (
            db.session.query(Expense)
            .filter_by(user_id=uid)
            .filter(Expense.category_id.is_(None))
            .all()
        )

    results = []
    for expense in expenses:
        result = categorize_expense(
            user_id=uid,
            description=expense.notes or "",
            amount=Decimal(str(expense.amount)),
        )
        if result["category_id"] is not None:
            expense.category_id = result["category_id"]
        results.append(
            {
                "expense_id": expense.id,
                "category_id": result["category_id"],
                "category_name": result["category_name"],
                "confidence": result["confidence"],
                "method": result["method"],
            }
        )

    db.session.commit()
    logger.info(
        "Bulk-categorized %s expenses for user=%s", len(results), uid
    )
    return jsonify({"categorized": len(results), "results": results})


# ---------------------------------------------------------------------------
# User correction (learning)
# ---------------------------------------------------------------------------


@bp.post("/expenses/<int:expense_id>/correct")
@jwt_required()
def correct_categorization(expense_id: int):
    uid = int(get_jwt_identity())
    expense = db.session.get(Expense, expense_id)
    if not expense or expense.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    category_id = data.get("category_id")
    if category_id is None:
        return jsonify(error="category_id required"), 400

    # Validate category belongs to this user
    cat = db.session.get(Category, int(category_id))
    if not cat or cat.user_id != uid:
        return jsonify(error="category not found"), 404

    # Apply to expense immediately
    expense.category_id = cat.id
    db.session.commit()

    # Record correction for learning
    record_correction(
        user_id=uid,
        expense_id=expense_id,
        description=expense.notes or "",
        category_id=cat.id,
    )

    logger.info(
        "User correction expense=%s user=%s cat=%s", expense_id, uid, cat.id
    )
    return jsonify(
        {
            "expense_id": expense_id,
            "category_id": cat.id,
            "category_name": cat.name,
            "message": "correction recorded and applied",
        }
    )


# ---------------------------------------------------------------------------
# Category rules CRUD
# ---------------------------------------------------------------------------


@bp.get("/rules")
@jwt_required()
def list_rules():
    uid = int(get_jwt_identity())
    rules = (
        db.session.query(CategoryRule)
        .filter_by(user_id=uid)
        .order_by(CategoryRule.priority.desc(), CategoryRule.id)
        .all()
    )
    return jsonify([_rule_to_dict(r) for r in rules])


@bp.post("/rules")
@jwt_required()
def create_rule():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    category_id = data.get("category_id")
    if not category_id:
        return jsonify(error="category_id required"), 400
    cat = db.session.get(Category, int(category_id))
    if not cat or cat.user_id != uid:
        return jsonify(error="category not found"), 404

    rule_type = str(data.get("rule_type") or "keyword").lower()
    if rule_type not in ("keyword", "merchant", "amount_range"):
        return jsonify(
            error="rule_type must be keyword, merchant, or amount_range"
        ), 400

    pattern = (data.get("pattern") or "").strip() or None
    amount_min = data.get("amount_min")
    amount_max = data.get("amount_max")
    priority = int(data.get("priority") or 0)

    if rule_type in ("keyword", "merchant") and not pattern:
        return jsonify(error="pattern required for keyword/merchant rules"), 400

    if rule_type == "amount_range" and amount_min is None and amount_max is None:
        return jsonify(error="amount_min or amount_max required for amount_range rules"), 400

    rule = CategoryRule(
        user_id=uid,
        category_id=cat.id,
        rule_type=rule_type,
        pattern=pattern,
        amount_min=Decimal(str(amount_min)) if amount_min is not None else None,
        amount_max=Decimal(str(amount_max)) if amount_max is not None else None,
        priority=priority,
    )
    db.session.add(rule)
    db.session.commit()

    logger.info("Created rule id=%s user=%s type=%s", rule.id, uid, rule_type)
    return jsonify(_rule_to_dict(rule)), 201


@bp.delete("/rules/<int:rule_id>")
@jwt_required()
def delete_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.get(CategoryRule, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(rule)
    db.session.commit()
    logger.info("Deleted rule id=%s user=%s", rule_id, uid)
    return jsonify(message="deleted")


# ---------------------------------------------------------------------------
# Default categories reference
# ---------------------------------------------------------------------------


@bp.get("/defaults")
@jwt_required()
def list_defaults():
    """Return the list of built-in default category names."""
    return jsonify({"default_categories": DEFAULT_CATEGORIES})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule_to_dict(r: CategoryRule) -> dict:
    return {
        "id": r.id,
        "category_id": r.category_id,
        "rule_type": r.rule_type,
        "pattern": r.pattern,
        "amount_min": float(r.amount_min) if r.amount_min is not None else None,
        "amount_max": float(r.amount_max) if r.amount_max is not None else None,
        "priority": r.priority,
        "created_at": r.created_at.isoformat(),
    }
