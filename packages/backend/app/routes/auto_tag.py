from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.auto_tag import (
    create_rule,
    update_rule,
    delete_rule,
    list_rules,
    record_feedback,
    get_learning_suggestions,
)
import logging

bp = Blueprint("auto_tag", __name__)
logger = logging.getLogger("finmind.auto_tag")


@bp.get("/rules")
@jwt_required()
def list_auto_tag_rules():
    uid = int(get_jwt_identity())
    rules = list_rules(uid)
    return jsonify([
        {
            "id": r.id,
            "name": r.name,
            "condition_field": r.condition_field,
            "condition_operator": r.condition_operator,
            "condition_value": r.condition_value,
            "target_category_id": r.target_category_id,
            "priority": r.priority,
            "active": r.active,
        }
        for r in rules
    ])


@bp.post("/rules")
@jwt_required()
def create_auto_tag_rule():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("name") or not data.get("condition_value"):
        return jsonify(error="name and condition_value required"), 400
    rule = create_rule(uid, data)
    logger.info("Created auto-tag rule id=%s user=%s", rule.id, uid)
    return jsonify(id=rule.id), 201


@bp.put("/rules/<int:rule_id>")
@jwt_required()
def update_auto_tag_rule(rule_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    rule = update_rule(rule_id, uid, data)
    if not rule:
        return jsonify(error="not found"), 404
    return jsonify(id=rule.id)


@bp.delete("/rules/<int:rule_id>")
@jwt_required()
def delete_auto_tag_rule(rule_id: int):
    uid = int(get_jwt_identity())
    if delete_rule(rule_id, uid):
        return jsonify(message="deleted")
    return jsonify(error="not found"), 404


@bp.post("/feedback")
@jwt_required()
def tag_feedback():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    expense_id = data.get("expense_id")
    old_category_id = data.get("old_category_id")
    new_category_id = data.get("new_category_id")
    rule_id = data.get("rule_id")
    if not expense_id:
        return jsonify(error="expense_id required"), 400
    fb = record_feedback(uid, expense_id, old_category_id, new_category_id, rule_id)
    return jsonify(id=fb.id), 201


@bp.get("/learning-suggestions")
@jwt_required()
def learning_suggestions():
    uid = int(get_jwt_identity())
    suggestions = get_learning_suggestions(uid)
    return jsonify(suggestions)
