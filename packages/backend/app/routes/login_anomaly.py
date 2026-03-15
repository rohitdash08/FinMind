"""Routes for login anomaly detection and security alerts."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.login_anomaly import (
    record_login_event,
    get_login_history,
    get_security_alerts,
    acknowledge_alert,
    acknowledge_all_alerts,
    get_login_stats,
)

bp = Blueprint("login_anomaly", __name__)


@bp.route("/record", methods=["POST"])
@jwt_required()
def record_event():
    """Record a login event and check for anomalies.

    JSON body:
    - event_type: login | failed_login | logout (default: login)
    - session_id: optional session identifier
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    ip_address = request.remote_addr or ""
    user_agent = request.headers.get("User-Agent", "")

    result = record_login_event(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        event_type=data.get("event_type", "login"),
        session_id=data.get("session_id", ""),
    )

    return jsonify(result), 201


@bp.route("/history", methods=["GET"])
@jwt_required()
def login_history():
    """Get login event history.

    Query params:
    - limit: max records (default 50)
    - event_type: filter by type
    - suspicious: true to show only suspicious events
    """
    user_id = int(get_jwt_identity())
    limit = request.args.get("limit", 50, type=int)
    event_type = request.args.get("event_type")
    suspicious = request.args.get("suspicious", "false").lower() == "true"

    events = get_login_history(user_id, limit, event_type, suspicious)
    return jsonify({"events": events, "count": len(events)}), 200


@bp.route("/alerts", methods=["GET"])
@jwt_required()
def security_alerts():
    """Get security alerts.

    Query params:
    - limit: max alerts (default 50)
    - unacknowledged: true to show only unacknowledged
    """
    user_id = int(get_jwt_identity())
    limit = request.args.get("limit", 50, type=int)
    unack = request.args.get("unacknowledged", "false").lower() == "true"

    alerts = get_security_alerts(user_id, limit, unack)
    return jsonify({"alerts": alerts, "count": len(alerts)}), 200


@bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
@jwt_required()
def ack_alert(alert_id):
    """Acknowledge a security alert."""
    user_id = int(get_jwt_identity())

    if acknowledge_alert(user_id, alert_id):
        return jsonify({"message": "Alert acknowledged"}), 200

    return jsonify({"error": "Alert not found"}), 404


@bp.route("/alerts/acknowledge-all", methods=["POST"])
@jwt_required()
def ack_all_alerts():
    """Acknowledge all unacknowledged alerts."""
    user_id = int(get_jwt_identity())
    count = acknowledge_all_alerts(user_id)
    return jsonify({"message": f"{count} alerts acknowledged", "count": count}), 200


@bp.route("/stats", methods=["GET"])
@jwt_required()
def login_stats():
    """Get login statistics.

    Query params:
    - days: lookback period (default 30)
    """
    user_id = int(get_jwt_identity())
    days = request.args.get("days", 30, type=int)

    stats = get_login_stats(user_id, days)
    return jsonify(stats), 200
