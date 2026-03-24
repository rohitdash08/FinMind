"""Login security alert management endpoints."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.login_anomaly import get_user_alerts, mark_alerts_read

bp = Blueprint("alerts", __name__)


@bp.get("/")
@jwt_required()
def list_alerts():
    """List login security alerts for the current user."""
    uid = int(get_jwt_identity())
    unread_only = request.args.get("unread", "false").lower() == "true"
    limit = min(int(request.args.get("limit", 50)), 100)
    alerts = get_user_alerts(uid, unread_only=unread_only, limit=limit)
    return jsonify(
        alerts=[
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "read": a.read,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]
    )


@bp.post("/read")
@jwt_required()
def mark_read():
    """Mark alerts as read. Body: {\"alert_ids\": [1,2,3]} or omit for all."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    alert_ids = data.get("alert_ids")
    count = mark_alerts_read(uid, alert_ids)
    return jsonify(marked_read=count)


@bp.get("/unread-count")
@jwt_required()
def unread_count():
    """Get count of unread alerts."""
    uid = int(get_jwt_identity())
    alerts = get_user_alerts(uid, unread_only=True)
    return jsonify(unread_count=len(alerts))
