import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Category, CategoryRule
from ..services.categorization import categorize_note, apply_correction, bulk_categorize

bp = Blueprint("categorization", __name__)
logger = logging.getLogger("finmind.categorization_routes")


@bp.post("/suggest")
@jwt_required()
def suggest_category():
    """
    Suggest a category for a transaction based on its notes.

    Body: { "note": "Swiggy order", "amount": 250.0 }
    Returns: { "category_id": 3, "category_name": "Food", "confidence": 0.95, "method": "user_rule" }
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    note = (data.get("note") or "").strip()
    amount = data.get("amount")

    if not note:
        return jsonify(error="note is required"), 400

    result = categorize_note(uid, note, float(amount) if amount else None)
    logger.info("Categorize suggest uid=%s note=%r -> %s", uid, note[:50], result["method"])
    return jsonify(result)


@bp.post("/correct")
@jwt_required()
def correct_category():
    """
    User corrects the category of an expense. Learns from correction.

    Body: { "expense_id": 42, "category_id": 7 }
    Returns: { "rule_created": true }
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    expense_id = data.get("expense_id")
    category_id = data.get("category_id")

    if not expense_id or not category_id:
        return jsonify(error="expense_id and category_id are required"), 400

    # Validate category belongs to user
    cat = db.session.query(Category).filter_by(id=category_id, user_id=uid).first()
    if not cat:
        return jsonify(error="category not found"), 404

    rule_created = apply_correction(uid, int(expense_id), int(category_id))
    logger.info("Correction applied uid=%s expense=%s cat=%s rule_created=%s",
                uid, expense_id, category_id, rule_created)
    return jsonify(rule_created=rule_created)


@bp.post("/bulk")
@jwt_required()
def bulk_suggest():
    """
    Auto-categorize multiple expenses. Applies categories with confidence >= 0.7.

    Body: { "expense_ids": [1, 2, 3] }
    Returns: [{ "expense_id": 1, "category_id": 3, "confidence": 0.85, "applied": true }, ...]
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    expense_ids = data.get("expense_ids", [])

    if not isinstance(expense_ids, list) or not expense_ids:
        return jsonify(error="expense_ids must be a non-empty list"), 400

    if len(expense_ids) > 100:
        return jsonify(error="maximum 100 expenses per request"), 400

    results = bulk_categorize(uid, [int(eid) for eid in expense_ids])
    applied = sum(1 for r in results if r.get("applied"))
    logger.info("Bulk categorize uid=%s count=%s applied=%s", uid, len(expense_ids), applied)
    return jsonify(results=results, total=len(results), applied=applied)


@bp.get("/rules")
@jwt_required()
def list_rules():
    """List all categorization rules for the current user."""
    uid = int(get_jwt_identity())
    rules = (
        db.session.query(CategoryRule)
        .filter_by(user_id=uid)
        .order_by(CategoryRule.priority.desc(), CategoryRule.created_at.desc())
        .all()
    )
    return jsonify([
        {
            "id": r.id,
            "category_id": r.category_id,
            "pattern": r.pattern,
            "match_type": r.match_type,
            "priority": r.priority,
            "active": r.active,
            "auto_generated": r.auto_generated,
        }
        for r in rules
    ])


@bp.post("/rules")
@jwt_required()
def create_rule():
    """
    Create a user-defined categorization rule.

    Body: {
        "category_id": 3,
        "pattern": "swiggy",
        "match_type": "contains",  // "exact" | "contains" | "regex"
        "priority": 10
    }
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    category_id = data.get("category_id")
    pattern = (data.get("pattern") or "").strip()
    match_type = data.get("match_type", "contains")
    priority = data.get("priority", 5)

    if not category_id or not pattern:
        return jsonify(error="category_id and pattern are required"), 400

    if match_type not in ("exact", "contains", "regex"):
        return jsonify(error="match_type must be exact, contains, or regex"), 400

    cat = db.session.query(Category).filter_by(id=category_id, user_id=uid).first()
    if not cat:
        return jsonify(error="category not found"), 404

    # Check for duplicate
    existing = db.session.query(CategoryRule).filter_by(
        user_id=uid, pattern=pattern.lower(), match_type=match_type
    ).first()
    if existing:
        return jsonify(error="rule already exists"), 409

    rule = CategoryRule(
        user_id=uid,
        category_id=int(category_id),
        pattern=pattern.lower(),
        match_type=match_type,
        priority=int(priority),
        active=True,
        auto_generated=False,
    )
    db.session.add(rule)
    db.session.commit()
    logger.info("Created rule id=%s user=%s pattern=%r", rule.id, uid, pattern)
    return jsonify(
        id=rule.id,
        category_id=rule.category_id,
        pattern=rule.pattern,
        match_type=rule.match_type,
        priority=rule.priority,
        active=rule.active,
        auto_generated=rule.auto_generated,
    ), 201


@bp.patch("/rules/<int:rule_id>")
@jwt_required()
def update_rule(rule_id: int):
    """Toggle a rule active/inactive or update its priority."""
    uid = int(get_jwt_identity())
    rule = db.session.query(CategoryRule).filter_by(id=rule_id, user_id=uid).first()
    if not rule:
        return jsonify(error="rule not found"), 404

    data = request.get_json() or {}
    if "active" in data:
        rule.active = bool(data["active"])
    if "priority" in data:
        rule.priority = int(data["priority"])
    db.session.commit()
    return jsonify(id=rule.id, active=rule.active, priority=rule.priority)


@bp.delete("/rules/<int:rule_id>")
@jwt_required()
def delete_rule(rule_id: int):
    """Delete a categorization rule."""
    uid = int(get_jwt_identity())
    rule = db.session.query(CategoryRule).filter_by(id=rule_id, user_id=uid).first()
    if not rule:
        return jsonify(error="rule not found"), 404
    db.session.delete(rule)
    db.session.commit()
    return jsonify(message="deleted")

