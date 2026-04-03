from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.auto_tag import (
    bulk_auto_tag, get_expense_tags, set_expense_tags, DEFAULT_RULES
)

tag_bp = Blueprint("tags", __name__, url_prefix="/tags")

@tag_bp.route("/auto", methods=["POST"])
@jwt_required()
def auto_tag():
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    months = int(body.get("months", 3))
    result = bulk_auto_tag(uid, months=months)
    return jsonify(result), 200

@tag_bp.route("/expense/<int:expense_id>", methods=["GET"])
@jwt_required()
def get_tags(expense_id):
    uid = int(get_jwt_identity())
    try:
        tags = get_expense_tags(uid, expense_id)
        return jsonify({"expense_id": expense_id, "tags": tags}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@tag_bp.route("/expense/<int:expense_id>", methods=["PUT"])
@jwt_required()
def set_tags(expense_id):
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    tags = body.get("tags", [])
    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list of strings"}), 400
    try:
        result = set_expense_tags(uid, expense_id, tags)
        return jsonify({"expense_id": expense_id, "tags": result}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@tag_bp.route("/rules", methods=["GET"])
@jwt_required()
def list_rules():
    rules = [{"tag": r.tag, "field": r.field, "match_type": r.match_type, "value": r.value} for r in DEFAULT_RULES]
    return jsonify({"count": len(rules), "rules": rules}), 200
