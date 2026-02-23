from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.login_anomaly import get_login_history, get_anomalies, acknowledge_anomaly

bp = Blueprint("security", __name__)


@bp.get("/login-history")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 50, type=int)
    limit = min(max(limit, 1), 200)
    events = get_login_history(uid, limit=limit)
    return jsonify(events=events)


@bp.get("/anomalies")
@jwt_required()
def anomalies():
    uid = int(get_jwt_identity())
    unack = request.args.get("unacknowledged_only", "false").lower() == "true"
    items = get_anomalies(uid, unacknowledged_only=unack)
    return jsonify(anomalies=items)


@bp.post("/anomalies/<int:anomaly_id>/acknowledge")
@jwt_required()
def acknowledge(anomaly_id: int):
    uid = int(get_jwt_identity())
    ok = acknowledge_anomaly(anomaly_id, uid)
    if not ok:
        return jsonify(error="anomaly not found"), 404
    return jsonify(message="acknowledged")
