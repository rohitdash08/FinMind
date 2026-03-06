from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.login_anomaly import get_login_history, get_anomalies, get_login_stats

bp = Blueprint("security", __name__)


@bp.get("/login-history")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)
    events = get_login_history(uid, limit=limit)
    return jsonify(events=events)


@bp.get("/anomalies")
@jwt_required()
def anomalies():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)
    events = get_anomalies(uid, limit=limit)
    return jsonify(anomalies=events)


@bp.get("/login-stats")
@jwt_required()
def login_stats():
    uid = int(get_jwt_identity())
    stats = get_login_stats(uid)
    return jsonify(stats)
