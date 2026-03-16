import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.categorization import (
    categorize_transaction,
    learn_from_correction,
    batch_categorize,
)

bp = Blueprint("categorize", __name__)
logger = logging.getLogger("finmind.categorize")


@bp.post("")
@jwt_required()
def categorize():
    """Categorize a single transaction by description."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    description = (data.get("description") or "").strip()
    if not description:
        return jsonify(error="description required"), 400
    category_id = data.get("category_id")
    result = categorize_transaction(
        description=description,
        existing_category_id=category_id,
        user_id=uid,
    )
    logger.info("Categorized user=%s desc=%s result=%s", uid, description[:50], result.get("category"))
    return jsonify(result)


@bp.post("/batch")
@jwt_required()
def categorize_batch():
    """Categorize multiple transactions at once."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    transactions = data.get("transactions")
    if not isinstance(transactions, list) or not transactions:
        return jsonify(error="transactions list required"), 400
    if len(transactions) > 100:
        return jsonify(error="maximum 100 transactions per batch"), 400
    results = batch_categorize(transactions, user_id=uid)
    logger.info("Batch categorized user=%s count=%s", uid, len(results))
    return jsonify(results=results, count=len(results))


@bp.post("/learn")
@jwt_required()
def learn():
    """Learn from a user's manual categorization correction."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    description = (data.get("description") or "").strip()
    category = (data.get("category") or "").strip()
    if not description:
        return jsonify(error="description required"), 400
    if not category:
        return jsonify(error="category required"), 400
    result = learn_from_correction(
        description=description,
        correct_category=category,
        user_id=uid,
    )
    logger.info("Learned user=%s cat=%s keywords=%s", uid, category, result.get("learned_count", 0))
    return jsonify(result)


@bp.get("/rules")
@jwt_required()
def list_rules():
    """List learned categorization rules for the current user."""
    uid = int(get_jwt_identity())
    from ..models import CategorizationRule as RuleModel
    from ..extensions import db

    rules = (
        db.session.query(RuleModel)
        .filter_by(user_id=uid)
        .order_by(RuleModel.confidence.desc())
        .all()
    )
    return jsonify([
        {
            "id": r.id,
            "keyword": r.keyword,
            "category": r.category_name,
            "confidence": round(r.confidence, 2),
            "source": r.source,
        }
        for r in rules
    ])


@bp.delete("/rules/<int:rule_id>")
@jwt_required()
def delete_rule(rule_id: int):
    """Delete a learned categorization rule."""
    uid = int(get_jwt_identity())
    from ..models import CategorizationRule as RuleModel
    from ..extensions import db

    rule = db.session.get(RuleModel, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(rule)
    db.session.commit()
    logger.info("Deleted rule id=%s user=%s", rule_id, uid)
    return jsonify(message="deleted")
