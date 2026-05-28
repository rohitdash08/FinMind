"""Rule-based auto tagging API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.rule_engine import (
    create_rule,
    apply_rules_to_transaction,
    get_user_rules,
    delete_rule,
)
from ..models_rules import TaggingRule

bp = Blueprint("rules", __name__)


@bp.get("/")
@jwt_required()
def list_rules():
    """List all tagging rules."""
    user_id = get_jwt_identity()
    rules = get_user_rules(user_id)
    return jsonify([r.to_dict() for r in rules])


@bp.post("/")
@jwt_required()
def add_rule():
    """Create a new tagging rule."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    required = ["name", "conditions"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    try:
        rule = create_rule(
            user_id=user_id,
            name=data["name"],
            conditions=data["conditions"],
            tag=data.get("tag"),
            category=data.get("category"),
            note=data.get("note"),
            priority=data.get("priority", 0),
        )
        return jsonify(rule.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/apply")
@jwt_required()
def apply_rules():
    """Apply rules to a transaction (preview)."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    if not data:
        return jsonify({"error": "Transaction data required"}), 400

    modifications = apply_rules_to_transaction(user_id, data)
    return jsonify(modifications)


@bp.put("/<int:rule_id>")
@jwt_required()
def update_rule(rule_id):
    """Update a tagging rule."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    rule = TaggingRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    for field in ["name", "is_active", "priority", "tag", "category", "note", "conditions"]:
        if field in data:
            setattr(rule, field, data[field])

    db.session.commit()
    return jsonify(rule.to_dict())


@bp.delete("/<int:rule_id>")
@jwt_required()
def remove_rule(rule_id):
    """Delete a tagging rule."""
    user_id = get_jwt_identity()
    if delete_rule(rule_id, user_id):
        return jsonify({"message": "Rule deleted"})
    return jsonify({"error": "Rule not found"}), 404
