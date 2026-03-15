"""Recurring transaction anomaly alert routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.recurring_anomaly import (
    check_anomaly,
    scan_all_recurring,
    get_alerts,
    acknowledge_alert,
    acknowledge_all_alerts,
    get_anomaly_summary,
    get_snapshots,
)

bp = Blueprint("recurring_anomaly", __name__)


@bp.post("/check")
@jwt_required()
def check_anomaly_route():
    """Check a single transaction for anomalies."""
    data = request.get_json()
    if not data or "recurring_id" not in data or "amount" not in data:
        return jsonify({"error": "recurring_id and amount are required"}), 400

    threshold = data.get("threshold_pct", 10.0)
    result = check_anomaly(data["recurring_id"], data["amount"], threshold)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@bp.post("/scan")
@jwt_required()
def scan_route():
    """Scan all recurring expenses for anomalies."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    threshold = data.get("threshold_pct", 10.0)
    result = scan_all_recurring(user_id, threshold)
    return jsonify(result), 200


@bp.get("/alerts")
@jwt_required()
def get_alerts_route():
    """Get anomaly alerts for the current user."""
    user_id = int(get_jwt_identity())
    unacked = request.args.get("unacknowledged", "false").lower() == "true"
    result = get_alerts(user_id, unacknowledged_only=unacked)
    return jsonify(result), 200


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def ack_alert(alert_id):
    """Acknowledge a single anomaly alert."""
    user_id = int(get_jwt_identity())
    result = acknowledge_alert(user_id, alert_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200


@bp.post("/alerts/acknowledge-all")
@jwt_required()
def ack_all():
    """Acknowledge all pending anomaly alerts."""
    user_id = int(get_jwt_identity())
    result = acknowledge_all_alerts(user_id)
    return jsonify(result), 200


@bp.get("/summary")
@jwt_required()
def summary_route():
    """Get anomaly summary for the current user."""
    user_id = int(get_jwt_identity())
    result = get_anomaly_summary(user_id)
    return jsonify(result), 200


@bp.get("/snapshots/<int:recurring_id>")
@jwt_required()
def snapshots_route(recurring_id):
    """Get price snapshots for a recurring expense."""
    limit = request.args.get("limit", 20, type=int)
    result = get_snapshots(recurring_id, limit=limit)
    return jsonify(result), 200
