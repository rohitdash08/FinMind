"""Security & login-anomaly routes (issue #124).

GET    /security/events                       login history (most recent first)
GET    /security/alerts                       all alerts (unread_only=true supported)
GET    /security/alerts/unread-count          count of unread alerts
PATCH  /security/alerts/<id>/acknowledge      mark alert as read
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.anomaly import (
    acknowledge_alert,
    alert_to_dict,
    event_to_dict,
    get_alerts,
    get_login_history,
)

bp = Blueprint("security", __name__)
logger = logging.getLogger("finmind.security.routes")


@bp.get("/events")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", 50)), 200)
    events = get_login_history(uid, limit=limit)
    return jsonify([event_to_dict(e) for e in events])


@bp.get("/alerts")
@jwt_required()
def list_alerts():
    uid = int(get_jwt_identity())
    unread_only = request.args.get("unread_only", "").lower() in ("1", "true", "yes")
    alerts = get_alerts(uid, unread_only=unread_only)
    return jsonify([alert_to_dict(a) for a in alerts])


@bp.get("/alerts/unread-count")
@jwt_required()
def unread_count():
    uid = int(get_jwt_identity())
    count = len(get_alerts(uid, unread_only=True))
    return jsonify(unread_count=count)


@bp.patch("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def ack_alert(alert_id: int):
    uid = int(get_jwt_identity())
    alert = acknowledge_alert(uid, alert_id)
    if not alert:
        return jsonify(error="alert not found"), 404
    return jsonify(alert_to_dict(alert))
