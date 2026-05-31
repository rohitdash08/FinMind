from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.anomaly_detector import (
    check_recurring_anomalies,
    list_alerts,
    acknowledge_alert,
)
import logging

bp = Blueprint("anomaly_alerts", __name__)
logger = logging.getLogger("finmind.anomaly_alerts")


@bp.get("")
@jwt_required()
def get_alerts():
    uid = int(get_jwt_identity())
    include_acknowledged = request.args.get("include_acknowledged", "false").lower() == "true"
    alerts = list_alerts(uid, include_acknowledged)
    return jsonify(alerts)


@bp.post("/check")
@jwt_required()
def run_check():
    uid = int(get_jwt_identity())
    alerts = check_recurring_anomalies(uid)
    logger.info("Anomaly check user=%s alerts=%s", uid, len(alerts))
    return jsonify(alerts), 201


@bp.post("/<int:alert_id>/acknowledge")
@jwt_required()
def ack_alert(alert_id: int):
    uid = int(get_jwt_identity())
    if acknowledge_alert(alert_id, uid):
        return jsonify(message="acknowledged")
    return jsonify(error="not found"), 404
