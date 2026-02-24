"""
alerts.py — Category budget management and overspend alert endpoints.

Endpoints:
    GET  /alerts/overspend              — current-month overspend warnings
    GET  /budgets                       — list all category budgets
    POST /budgets/<int:category_id>     — set/update monthly limit
    DELETE /budgets/<int:category_id>   — remove a budget
"""
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Category, CategoryBudget
from ..services.overspend import budget_to_dict, check_category_warnings

bp_alerts = Blueprint("alerts", __name__)
bp_budgets = Blueprint("budgets", __name__)
logger = logging.getLogger("finmind.alerts")


# ── Overspend alerts ──────────────────────────────────────────────────────────

@bp_alerts.get("/overspend")
@jwt_required()
def get_overspend_alerts():
    """Return current-month categories that are at or near their budget limit."""
    uid = int(get_jwt_identity())
    warnings = check_category_warnings(uid, db.session)
    return jsonify({
        "count": len(warnings),
        "warnings": warnings,
    })


# ── Budget management ─────────────────────────────────────────────────────────

@bp_budgets.get("")
@jwt_required()
def list_budgets():
    """List all category budgets for the current user."""
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(CategoryBudget, Category.name)
        .join(Category, CategoryBudget.category_id == Category.id)
        .filter(CategoryBudget.user_id == uid)
        .order_by(Category.name)
        .all()
    )
    return jsonify([budget_to_dict(b, name) for b, name in rows])


@bp_budgets.post("/<int:category_id>")
@jwt_required()
def set_budget(category_id: int):
    """
    Set or update a monthly budget limit for a category.

    Body: { "monthly_limit": 5000.0, "currency": "INR" }
    """
    uid = int(get_jwt_identity())
    cat = db.session.get(Category, category_id)
    if not cat or cat.user_id != uid:
        return jsonify(error="category not found"), 404

    data = request.get_json() or {}
    try:
        limit = float(data["monthly_limit"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="monthly_limit (number) required"), 400
    if limit <= 0:
        return jsonify(error="monthly_limit must be positive"), 400

    currency = str(data.get("currency") or "INR").upper()[:10]

    existing = (
        db.session.query(CategoryBudget)
        .filter_by(user_id=uid, category_id=category_id)
        .first()
    )
    if existing:
        existing.monthly_limit = limit
        existing.currency = currency
        existing.updated_at = datetime.utcnow()
        db.session.commit()
        logger.info("Updated budget cat=%s user=%s limit=%.2f", category_id, uid, limit)
        return jsonify(budget_to_dict(existing, cat.name))
    else:
        budget = CategoryBudget(
            user_id=uid,
            category_id=category_id,
            monthly_limit=limit,
            currency=currency,
        )
        db.session.add(budget)
        db.session.commit()
        logger.info("Created budget cat=%s user=%s limit=%.2f", category_id, uid, limit)
        return jsonify(budget_to_dict(budget, cat.name)), 201


@bp_budgets.delete("/<int:category_id>")
@jwt_required()
def delete_budget(category_id: int):
    """Remove a category budget."""
    uid = int(get_jwt_identity())
    budget = (
        db.session.query(CategoryBudget)
        .filter_by(user_id=uid, category_id=category_id)
        .first()
    )
    if not budget:
        return jsonify(error="not found"), 404
    db.session.delete(budget)
    db.session.commit()
    logger.info("Deleted budget cat=%s user=%s", category_id, uid)
    return jsonify(message="deleted")
