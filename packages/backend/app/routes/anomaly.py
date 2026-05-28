"""Login anomaly detection endpoints for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import anomaly as anomaly_service

bp = Blueprint("anomaly", __name__)


@bp.get("/alerts")
@jwt_required()
def get_my_alerts():
    """Get anomaly alerts for the current user."""
    uid = int(get_jwt_identity())
    try:
        limit = min(50, max(1, int(request.args.get("limit", "20"))))
    except ValueError:
        limit = 20
    alerts = anomaly_service.get_alerts(uid, limit=limit)
    return jsonify(alerts)


@bp.delete("/alerts")
@jwt_required()
def clear_my_alerts():
    """Clear all anomaly alerts for the current user."""
    uid = int(get_jwt_identity())
    count = anomaly_service.clear_alerts(uid)
    return jsonify(cleared=count)
