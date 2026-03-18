"""
Security / anomaly-detection routes
=====================================
User-facing:
  GET  /security/login-history          — paginated login history for current user
  GET  /security/alerts                 — unacknowledged suspicious-login alerts
  POST /security/alerts/<id>/acknowledge — dismiss an alert

Admin-only (role == ADMIN):
  GET  /admin/login-events              — all login events across all users
  GET  /admin/login-alerts              — all login alerts across all users
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Role, User
from ..services import login_anomaly as anomaly_svc

bp = Blueprint("security", __name__)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _current_user() -> User | None:
    uid = int(get_jwt_identity())
    return db.session.get(User, uid)


def _require_admin():
    user = _current_user()
    if not user or user.role != Role.ADMIN.value:
        return jsonify(error="admin access required"), 403
    return None


# --------------------------------------------------------------------------- #
# User-facing endpoints                                                        #
# --------------------------------------------------------------------------- #

@bp.get("/login-history")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", 50)), 200)
    history = anomaly_svc.get_login_history(uid, limit=limit)
    return jsonify(login_events=history, count=len(history))


@bp.get("/alerts")
@jwt_required()
def list_alerts():
    uid = int(get_jwt_identity())
    include_acked = request.args.get("include_acknowledged", "false").lower() == "true"
    alerts = anomaly_svc.get_alerts(uid, include_acknowledged=include_acked)
    return jsonify(alerts=alerts, count=len(alerts))


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def acknowledge_alert(alert_id: int):
    uid = int(get_jwt_identity())
    alert = anomaly_svc.acknowledge_alert(alert_id, uid)
    if alert is None:
        return jsonify(error="alert not found"), 404
    return jsonify(alert)


# --------------------------------------------------------------------------- #
# Admin endpoints                                                              #
# --------------------------------------------------------------------------- #

@bp.get("/admin/login-events")
@jwt_required()
def admin_login_events():
    err = _require_admin()
    if err:
        return err
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))
    events = anomaly_svc.admin_get_all_events(limit=limit, offset=offset)
    return jsonify(login_events=events, count=len(events))


@bp.get("/admin/login-alerts")
@jwt_required()
def admin_login_alerts():
    err = _require_admin()
    if err:
        return err
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))
    alerts = anomaly_svc.admin_get_all_alerts(limit=limit, offset=offset)
    return jsonify(alerts=alerts, count=len(alerts))
