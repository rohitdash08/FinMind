from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.login_anomaly import (
    get_user_alerts, mark_alerts_read, get_login_history
)

bp = Blueprint("security", __name__)


@bp.get("/alerts")
@jwt_required()
def list_alerts():
    uid = int(get_jwt_identity())
    unread_only = request.args.get("unread", "false").lower() == "true"
    alerts = get_user_alerts(uid, unread_only=unread_only)
    return jsonify([{
        "id": a.id, "alert_type": a.alert_type, "message": a.message,
        "severity": a.severity, "is_read": a.is_read,
        "created_at": a.created_at.isoformat(),
    } for a in alerts])


@bp.post("/alerts/mark-read")
@jwt_required()
def mark_read():
    uid = int(get_jwt_identity())
    data = request.get_json(force=True) if request.data else {}
    alert_ids = data.get("alert_ids")
    mark_alerts_read(uid, alert_ids)
    return jsonify(message="alerts marked as read")


@bp.get("/login-history")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    limit = int(request.args.get("limit", 20))
    events = get_login_history(uid, limit=limit)
    return jsonify([{
        "id": e.id, "ip_address": e.ip_address,
        "user_agent": e.user_agent, "location": e.location,
        "created_at": e.created_at.isoformat(),
    } for e in events])
