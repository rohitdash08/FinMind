"""Routes for login security: history, alerts, and acknowledgement."""

from __future__ import annotations

import json
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.login_anomaly import (
    acknowledge_alert,
    get_alerts,
    get_recent_attempts,
)

bp = Blueprint("login_security", __name__)


@bp.get("/history")
@jwt_required()
def login_history():
    """Return recent login attempts for the authenticated user."""
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)
    limit = min(max(limit, 1), 100)
    attempts = get_recent_attempts(uid, limit=limit)
    return jsonify([
        {
            "id": a.id,
            "ip_address": a.ip_address,
            "user_agent": a.user_agent,
            "success": a.success,
            "country": a.country,
            "created_at": a.created_at.isoformat() + "Z",
        }
        for a in attempts
    ])


@bp.get("/alerts")
@jwt_required()
def login_alerts():
    """Return unacknowledged login alerts for the authenticated user."""
    uid = int(get_jwt_identity())
    include_ack = request.args.get("include_acknowledged", "false").lower() == "true"
    alerts = get_alerts(uid, include_acknowledged=include_ack)
    return jsonify([
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "metadata": json.loads(a.metadata_json) if a.metadata_json else None,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat() + "Z",
        }
        for a in alerts
    ])


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def acknowledge(alert_id: int):
    """Mark a specific alert as acknowledged."""
    uid = int(get_jwt_identity())
    alert = acknowledge_alert(alert_id, uid)
    if alert is None:
        return jsonify(error="alert not found"), 404
    return jsonify(message="acknowledged", alert_id=alert.id)
