from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.auto_tag import (
    create_rule,
    list_rules,
    update_rule,
    delete_rule,
    apply_all_rules,
    learn_from_correction,
)
import logging

bp = Blueprint("auto_tag", __name__)
logger = logging.getLogger("finmind.auto_tag")


@bp.get("/rules")
@jwt_required()
def get_rules():
    uid = int(get_jwt_identity())
    rules = list_rules(uid)
    return jsonify(
        [
            {
                "id": r.id,
                "name": r.name,
                "rule_type": r.rule_type,
                "match_value": r.match_value,
                "target_category_id": r.target_category_id,
                "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in rules
        ]
    )


@bp.post("/rules")
@jwt_required()
def post_rule():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("name") or not data.get("rule_type") or not data.get("match_value"):
        return jsonify(error="name, rule_type, match_value required"), 400
    if str(data["rule_type"]).upper() not in {"CATEGORY", "KEYWORD"}:
        return jsonify(error="rule_type must be CATEGORY or KEYWORD"), 400
    rule = create_rule(uid, data)
    return jsonify(id=rule.id), 201


@bp.patch("/rules/<int:rule_id>")
@jwt_required()
def patch_rule(rule_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    rule = update_rule(uid, rule_id, data)
    if not rule:
        return jsonify(error="not found"), 404
    return jsonify(id=rule.id)


@bp.delete("/rules/<int:rule_id>")
@jwt_required()
def delete_rule_route(rule_id: int):
    uid = int(get_jwt_identity())
    if not delete_rule(uid, rule_id):
        return jsonify(error="not found"), 404
    return jsonify(message="deleted")


@bp.post("/apply")
@jwt_required()
def apply_rules():
    uid = int(get_jwt_identity())
    count = apply_all_rules(uid)
    return jsonify(applied=count)


@bp.post("/learn")
@jwt_required()
def learn():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    expense_id = data.get("expense_id")
    category_id = data.get("category_id")
    if not expense_id or not category_id:
        return jsonify(error="expense_id and category_id required"), 400
    result = learn_from_correction(uid, int(expense_id), int(category_id))
    if "error" in result:
        return jsonify(error=result["error"]), 404
    return jsonify(result), 200
