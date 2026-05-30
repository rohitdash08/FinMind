import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.anomaly_detection import (
    acknowledge_alert,
    get_login_history,
    list_alerts,
)

bp = Blueprint("anomaly", __name__)
logger = logging.getLogger("finmind.anomaly")


@bp.get("/alerts")
@jwt_required()
def list_suspicious_alerts():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 50, type=int)
    alerts = list_alerts(uid, limit=min(limit, 200))
    logger.info("List alerts user=%s count=%s", uid, len(alerts))
    return jsonify(alerts)


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def acknowledge_suspicious_alert(alert_id: int):
    uid = int(get_jwt_identity())
    if not acknowledge_alert(alert_id, uid):
        return jsonify(error="not found"), 404
    return jsonify(message="acknowledged"), 200


@bp.get("/login-history")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)
    history = get_login_history(uid, limit=min(limit, 100))
    logger.info("Login history user=%s count=%s", uid, len(history))
    return jsonify(history)
