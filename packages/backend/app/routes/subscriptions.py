"""Subscription detection and monitoring API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.subscription_detector import (
    detect_subscriptions,
    get_user_subscriptions,
    get_cost_alerts,
    confirm_subscription,
    dismiss_subscription,
    mark_alert_read,
)

bp = Blueprint("subscriptions", __name__)


@bp.get("/")
@jwt_required()
def list_subscriptions():
    """List detected subscriptions."""
    user_id = get_jwt_identity()
    active = request.args.get("active", "true").lower() == "true"
    subs = get_user_subscriptions(user_id, active_only=active)
    return jsonify([s.to_dict() for s in subs])


@bp.post("/detect")
@jwt_required()
def run_detection():
    """Run subscription detection on transactions."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    transactions = data.get("transactions", [])
    if not transactions:
        return jsonify({"error": "No transactions provided"}), 400

    results = detect_subscriptions(user_id, transactions)
    return jsonify({
        "detected": len(results),
        "subscriptions": [s.to_dict() for s in results],
    })


@bp.post("/<int:sub_id>/confirm")
@jwt_required()
def confirm(sub_id):
    """Confirm a detected subscription."""
    user_id = get_jwt_identity()
    try:
        sub = confirm_subscription(sub_id, user_id)
        return jsonify(sub.to_dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.post("/<int:sub_id>/dismiss")
@jwt_required()
def dismiss(sub_id):
    """Dismiss a false positive."""
    user_id = get_jwt_identity()
    if dismiss_subscription(sub_id, user_id):
        return jsonify({"message": "Subscription dismissed"})
    return jsonify({"error": "Not found"}), 404


@bp.get("/alerts")
@jwt_required()
def list_alerts():
    """List subscription cost increase alerts."""
    user_id = get_jwt_identity()
    unread = request.args.get("unread", "false").lower() == "true"
    alerts = get_cost_alerts(user_id, unread_only=unread)
    return jsonify([a.to_dict() for a in alerts])


@bp.post("/alerts/<int:alert_id>/read")
@jwt_required()
def read_alert(alert_id):
    """Mark cost alert as read."""
    user_id = get_jwt_identity()
    if mark_alert_read(alert_id, user_id):
        return jsonify({"message": "Alert marked as read"})
    return jsonify({"error": "Not found"}), 404
