"""Login Anomaly Detection API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.login_anomaly import LoginAnomalyService

bp = Blueprint("login_anomaly", __name__)

svc = LoginAnomalyService()


@bp.post("/record")
@jwt_required()
def record_login():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    return jsonify(svc.record_login(
        user_id=user_id,
        ip=data.get("ip", request.remote_addr),
        user_agent=request.headers.get("User-Agent", ""),
        location=data.get("location"),
        latitude=data.get("latitude", type=float),
        longitude=data.get("longitude", type=float),
    ))


@bp.post("/failed")
def record_failed():
    data = request.get_json() or {}
    return jsonify(svc.record_failed_login(
        ip=data.get("ip", request.remote_addr),
        user_id=data.get("user_id"),
    ))


@bp.get("/history")
@jwt_required()
def get_history():
    user_id = str(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)
    return jsonify(svc.get_login_history(user_id, limit))


@bp.get("/alerts")
@jwt_required()
def get_alerts():
    user_id = str(get_jwt_identity())
    severity = request.args.get("severity")
    return jsonify(svc.get_alerts(user_id, severity))


@bp.post("/trust-device")
@jwt_required()
def trust_device():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    return jsonify(svc.trust_device(user_id, data.get("fingerprint", "")))
