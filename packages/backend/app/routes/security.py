"""Login anomaly detection & suspicious activity alerts API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.login_anomaly import (
    record_login, get_login_history, get_alerts,
    acknowledge_alert, get_security_summary,
)
import logging

bp = Blueprint("security", __name__)
logger = logging.getLogger("finmind.security")


@bp.post("/login-event")
@jwt_required()
def log_login():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    ip = data.get("ip_address", request.remote_addr or "0.0.0.0")
    result = record_login(
        uid, ip, data.get("user_agent", ""),
        data.get("country", "unknown"), data.get("city", "unknown"),
        data.get("success", True),
    )
    return jsonify(result), 201


@bp.get("/login-history")
@jwt_required()
def history():
    uid = int(get_jwt_identity())
    limit = int(request.args.get("limit", 50))
    return jsonify(get_login_history(uid, limit))


@bp.get("/alerts")
@jwt_required()
def alerts():
    uid = int(get_jwt_identity())
    unack = request.args.get("unacknowledged", "false").lower() == "true"
    return jsonify(get_alerts(uid, unack))


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def ack_alert(alert_id):
    uid = int(get_jwt_identity())
    if acknowledge_alert(uid, alert_id):
        return jsonify({"message": "Alert acknowledged"})
    return jsonify({"error": "Alert not found"}), 404


@bp.get("/summary")
@jwt_required()
def summary():
    uid = int(get_jwt_identity())
    days = int(request.args.get("days", 30))
    return jsonify(get_security_summary(uid, days))
