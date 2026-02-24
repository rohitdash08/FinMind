import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AutoTagRule, Category

bp = Blueprint("rules", __name__)
logger = logging.getLogger("finmind.rules")

VALID_CONDITION_TYPES = {"keyword_match", "merchant_match", "amount_range"}


def _validate_conditions(conditions) -> str | None:
    """Return error message or None if valid."""
    if not isinstance(conditions, list) or len(conditions) == 0:
        return "conditions must be a non-empty list"
    for i, c in enumerate(conditions):
        if not isinstance(c, dict):
            return f"condition[{i}] must be an object"
        ctype = c.get("type")
        if ctype not in VALID_CONDITION_TYPES:
            return f"condition[{i}]: invalid type '{ctype}'"
        if ctype in ("keyword_match", "merchant_match"):
            if not (c.get("value") or "").strip():
                return f"condition[{i}]: value required for {ctype}"
        if ctype == "amount_range":
            mn, mx = c.get("min"), c.get("max")
            if mn is None and mx is None:
                return f"condition[{i}]: min or max required for amount_range"
            if mn is not None and not isinstance(mn, (int, float)):
                return f"condition[{i}]: min must be a number"
            if mx is not None and not isinstance(mx, (int, float)):
                return f"condition[{i}]: max must be a number"
            if mn is not None and mx is not None and mn > mx:
                return f"condition[{i}]: min must be <= max"
    return None


def _rule_to_dict(r: AutoTagRule) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "conditions": r.conditions,
        "target_category_id": r.target_category_id,
        "priority": r.priority,
        "active": r.active,
    }


@bp.get("")
@jwt_required()
def list_rules():
    uid = int(get_jwt_identity())
    rules = (
        db.session.query(AutoTagRule)
        .filter_by(user_id=uid)
        .order_by(AutoTagRule.priority.desc(), AutoTagRule.id.asc())
        .all()
    )
    logger.info("List rules user=%s count=%s", uid, len(rules))
    return jsonify([_rule_to_dict(r) for r in rules])


@bp.post("")
@jwt_required()
def create_rule():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    conditions = data.get("conditions")
    err = _validate_conditions(conditions)
    if err:
        return jsonify(error=err), 400
    target_category_id = data.get("target_category_id")
    if not target_category_id:
        return jsonify(error="target_category_id required"), 400
    cat = db.session.get(Category, int(target_category_id))
    if not cat or cat.user_id != uid:
        return jsonify(error="target category not found"), 404
    rule = AutoTagRule(
        user_id=uid,
        name=name,
        conditions=conditions,
        target_category_id=int(target_category_id),
        priority=int(data.get("priority", 0)),
        active=bool(data.get("active", True)),
    )
    db.session.add(rule)
    db.session.commit()
    logger.info("Created rule id=%s user=%s", rule.id, uid)
    return jsonify(_rule_to_dict(rule)), 201


@bp.patch("/<int:rule_id>")
@jwt_required()
def update_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.get(AutoTagRule, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        rule.name = name
    if "conditions" in data:
        err = _validate_conditions(data["conditions"])
        if err:
            return jsonify(error=err), 400
        rule.conditions = data["conditions"]
    if "target_category_id" in data:
        cat = db.session.get(Category, int(data["target_category_id"]))
        if not cat or cat.user_id != uid:
            return jsonify(error="target category not found"), 404
        rule.target_category_id = int(data["target_category_id"])
    if "priority" in data:
        rule.priority = int(data["priority"])
    if "active" in data:
        rule.active = bool(data["active"])
    db.session.commit()
    logger.info("Updated rule id=%s user=%s", rule.id, uid)
    return jsonify(_rule_to_dict(rule))


@bp.delete("/<int:rule_id>")
@jwt_required()
def delete_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.get(AutoTagRule, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(rule)
    db.session.commit()
    logger.info("Deleted rule id=%s user=%s", rule.id, uid)
    return jsonify(message="deleted")
