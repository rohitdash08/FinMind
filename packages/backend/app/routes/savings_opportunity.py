"""Routes for savings opportunity detection engine."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.savings_opportunity import (
    run_full_detection,
    get_opportunities,
    get_opportunity,
    dismiss_opportunity,
    mark_action_taken,
    get_savings_summary,
)

bp = Blueprint("savings_opportunity", __name__)


@bp.post("/detect")
@jwt_required()
def detect():
    """Run savings detection algorithms."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    days = int(data.get("days", 30))
    results = run_full_detection(user_id, days=days)
    return jsonify({
        "opportunities": results,
        "count": len(results),
        "period_days": days,
    }), 200


@bp.get("")
@jwt_required()
def list_opportunities():
    """List saved opportunities."""
    user_id = int(get_jwt_identity())
    results = get_opportunities(
        user_id,
        type=request.args.get("type"),
        status=request.args.get("status"),
        limit=int(request.args.get("limit", 50)),
    )
    return jsonify({
        "opportunities": results,
        "count": len(results),
    }), 200


@bp.get("/<int:opportunity_id>")
@jwt_required()
def get_one(opportunity_id):
    """Get a single opportunity."""
    user_id = int(get_jwt_identity())
    result = get_opportunity(opportunity_id, user_id)
    if not result:
        return jsonify({"error": "Opportunity not found"}), 404
    return jsonify(result), 200


@bp.post("/<int:opportunity_id>/dismiss")
@jwt_required()
def dismiss(opportunity_id):
    """Dismiss an opportunity."""
    user_id = int(get_jwt_identity())
    result = dismiss_opportunity(opportunity_id, user_id)
    if not result:
        return jsonify({"error": "Opportunity not found"}), 404
    return jsonify(result), 200


@bp.post("/<int:opportunity_id>/act")
@jwt_required()
def act(opportunity_id):
    """Mark action taken on an opportunity."""
    user_id = int(get_jwt_identity())
    result = mark_action_taken(opportunity_id, user_id)
    if not result:
        return jsonify({"error": "Opportunity not found"}), 404
    return jsonify(result), 200


@bp.get("/summary")
@jwt_required()
def summary():
    """Get savings opportunity summary."""
    user_id = int(get_jwt_identity())
    result = get_savings_summary(user_id)
    return jsonify(result), 200
