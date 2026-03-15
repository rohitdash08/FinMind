"""Routes for lifestyle inflation detection insights."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.lifestyle_inflation import (
    generate_snapshot,
    detect_inflation,
    get_trends,
    get_alerts,
    acknowledge_alert,
    get_inflation_summary,
)

bp = Blueprint("lifestyle_inflation", __name__)


@bp.post("/snapshot")
@jwt_required()
def create_snapshot():
    """Generate a spending snapshot for a period."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    period_start = data.get("period_start")
    period_end = data.get("period_end")
    if not period_start or not period_end:
        return jsonify({"error": "period_start and period_end are required"}), 400

    from datetime import date
    try:
        start = date.fromisoformat(period_start)
        end = date.fromisoformat(period_end)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    result = generate_snapshot(user_id, start, end)
    return jsonify(result), 201


@bp.post("/detect")
@jwt_required()
def detect():
    """Run inflation detection algorithms."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    months = int(data.get("months", 6))
    alerts = detect_inflation(user_id, months=months)
    return jsonify({
        "alerts": alerts,
        "count": len(alerts),
        "months_analyzed": months,
    }), 200


@bp.get("/trends")
@jwt_required()
def trends():
    """Get spending trends over time."""
    user_id = int(get_jwt_identity())
    months = int(request.args.get("months", 6))
    result = get_trends(user_id, months=months)
    return jsonify(result), 200


@bp.get("/alerts")
@jwt_required()
def list_alerts():
    """List inflation alerts."""
    user_id = int(get_jwt_identity())

    acknowledged = request.args.get("acknowledged")
    if acknowledged is not None:
        acknowledged = acknowledged.lower() in ("true", "1", "yes")

    result = get_alerts(
        user_id,
        alert_type=request.args.get("type"),
        severity=request.args.get("severity"),
        acknowledged=acknowledged,
        limit=int(request.args.get("limit", 50)),
    )
    return jsonify({"alerts": result, "count": len(result)}), 200


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def ack_alert(alert_id):
    """Acknowledge an alert."""
    user_id = int(get_jwt_identity())
    result = acknowledge_alert(alert_id, user_id)
    if not result:
        return jsonify({"error": "Alert not found"}), 404
    return jsonify(result), 200


@bp.get("/summary")
@jwt_required()
def summary():
    """Get inflation analysis summary."""
    user_id = int(get_jwt_identity())
    months = int(request.args.get("months", 6))
    result = get_inflation_summary(user_id, months=months)
    return jsonify(result), 200
