"""Subscription cost increase detection routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.subscription_cost import (
    update_plan_price,
    get_price_history,
    get_all_price_changes,
    get_user_alerts,
    acknowledge_alert,
    acknowledge_all_alerts,
    get_user_cost_summary,
    detect_increases,
)

bp = Blueprint("subscription_cost", __name__)


@bp.put("/plans/<int:plan_id>/price")
@jwt_required()
def update_price(plan_id):
    """Update subscription plan price and detect increases."""
    data = request.get_json()
    if not data or "price_cents" not in data:
        return jsonify({"error": "price_cents is required"}), 400

    result = update_plan_price(plan_id, data["price_cents"])
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@bp.get("/plans/<int:plan_id>/price-history")
@jwt_required()
def price_history(plan_id):
    """Get price change history for a plan."""
    limit = request.args.get("limit", 20, type=int)
    result = get_price_history(plan_id, limit=limit)
    return jsonify(result), 200


@bp.get("/price-changes")
@jwt_required()
def all_price_changes():
    """Get recent price changes across all plans."""
    limit = request.args.get("limit", 50, type=int)
    result = get_all_price_changes(limit=limit)
    return jsonify(result), 200


@bp.get("/alerts")
@jwt_required()
def user_alerts():
    """Get cost increase alerts for the current user."""
    user_id = int(get_jwt_identity())
    unacked = request.args.get("unacknowledged", "false").lower() == "true"
    result = get_user_alerts(user_id, unacknowledged_only=unacked)
    return jsonify(result), 200


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def ack_alert(alert_id):
    """Acknowledge a cost increase alert."""
    user_id = int(get_jwt_identity())
    result = acknowledge_alert(user_id, alert_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@bp.post("/alerts/acknowledge-all")
@jwt_required()
def ack_all():
    """Acknowledge all pending alerts."""
    user_id = int(get_jwt_identity())
    result = acknowledge_all_alerts(user_id)
    return jsonify(result), 200


@bp.get("/summary")
@jwt_required()
def cost_summary():
    """Get subscription cost summary for the current user."""
    user_id = int(get_jwt_identity())
    result = get_user_cost_summary(user_id)
    return jsonify(result), 200


@bp.get("/increases")
@jwt_required()
def increases():
    """Detect price increases, optionally for a specific plan."""
    plan_id = request.args.get("plan_id", type=int)
    result = detect_increases(plan_id=plan_id)
    return jsonify(result), 200
