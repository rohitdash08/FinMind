"""Rule-based Auto Tagging & Categorization routes.

Endpoints:
  POST   /tagging/rules           — create a tagging rule
  GET    /tagging/rules           — list rules
  GET    /tagging/rules/<id>      — get a single rule
  PUT    /tagging/rules/<id>      — update a rule
  DELETE /tagging/rules/<id>      — delete a rule
  POST   /tagging/test            — dry-run: test rules against expense data
  POST   /tagging/apply           — bulk-apply rules to uncategorized expenses
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.tagging import (
    create_rule,
    update_rule,
    delete_rule,
    get_rule,
    list_rules,
    test_rules_against_expense,
    bulk_apply_rules,
)

bp = Blueprint("tagging", __name__)


@bp.route("/rules", methods=["POST"])
@jwt_required()
def create():
    """Create a new tagging rule."""
    uid = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    name = data.get("name")
    match_pattern = data.get("match_pattern")

    if not name or not match_pattern:
        return jsonify({"error": "name and match_pattern are required"}), 400

    min_amt = None
    if data.get("min_amount") is not None:
        try:
            min_amt = Decimal(str(data["min_amount"]))
        except (InvalidOperation, ValueError):
            return jsonify({"error": "Invalid min_amount"}), 400

    max_amt = None
    if data.get("max_amount") is not None:
        try:
            max_amt = Decimal(str(data["max_amount"]))
        except (InvalidOperation, ValueError):
            return jsonify({"error": "Invalid max_amount"}), 400

    result = create_rule(
        user_id=uid,
        name=name,
        match_pattern=match_pattern,
        match_field=data.get("match_field", "notes"),
        match_type=data.get("match_type", "contains"),
        min_amount=min_amt,
        max_amount=max_amt,
        currency=data.get("currency"),
        assign_category_id=data.get("assign_category_id"),
        assign_tags=data.get("assign_tags"),
        priority=data.get("priority", 0),
        auto_apply=data.get("auto_apply", True),
    )

    if result is None:
        return jsonify({"error": "Invalid category_id"}), 400
    return jsonify(result), 201


@bp.route("/rules", methods=["GET"])
@jwt_required()
def list_all():
    """List all tagging rules."""
    uid = get_jwt_identity()
    active = request.args.get("active", "false").lower() == "true"
    return jsonify(list_rules(uid, active_only=active)), 200


@bp.route("/rules/<int:rule_id>", methods=["GET"])
@jwt_required()
def get_one(rule_id: int):
    """Get a single rule."""
    uid = get_jwt_identity()
    result = get_rule(uid, rule_id)
    if not result:
        return jsonify({"error": "Rule not found"}), 404
    return jsonify(result), 200


@bp.route("/rules/<int:rule_id>", methods=["PUT"])
@jwt_required()
def update(rule_id: int):
    """Update a tagging rule."""
    uid = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    result = update_rule(uid, rule_id, data)
    if not result:
        return jsonify({"error": "Rule not found"}), 404
    return jsonify(result), 200


@bp.route("/rules/<int:rule_id>", methods=["DELETE"])
@jwt_required()
def delete(rule_id: int):
    """Delete a tagging rule."""
    uid = get_jwt_identity()
    if delete_rule(uid, rule_id):
        return jsonify({"message": "Rule deleted"}), 200
    return jsonify({"error": "Rule not found"}), 404


@bp.route("/test", methods=["POST"])
@jwt_required()
def test_match():
    """Dry-run: test which rules would match given expense data.

    Body: { "notes": "Uber ride", "amount": 25, "currency": "USD" }
    """
    uid = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    matches = test_rules_against_expense(uid, data)
    return jsonify({"matches": matches, "count": len(matches)}), 200


@bp.route("/apply", methods=["POST"])
@jwt_required()
def apply_all():
    """Bulk-apply active rules to all uncategorized expenses."""
    uid = get_jwt_identity()
    result = bulk_apply_rules(uid)
    return jsonify(result), 200
