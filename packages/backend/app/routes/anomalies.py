from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.anomalies import check_recurring_anomalies, list_alerts, dismiss_alert
import logging

bp = Blueprint("anomalies", __name__)
logger = logging.getLogger("finmind.anomalies")


@bp.get("")
@jwt_required()
def get_alerts():
    uid = int(get_jwt_identity())
    alerts = list_alerts(uid)
    return jsonify(alerts)


@bp.post("/check")
@jwt_required()
def check():
    uid = int(get_jwt_identity())
    alerts = check_recurring_anomalies(uid)
    return jsonify(alerts=alerts, count=len(alerts))


@bp.patch("/<int:alert_id>/dismiss")
@jwt_required()
def dismiss(alert_id: int):
    uid = int(get_jwt_identity())
    if not dismiss_alert(uid, alert_id):
        return jsonify(error="not found"), 404
    return jsonify(message="dismissed")
