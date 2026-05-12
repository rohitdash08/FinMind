from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import LoginAnomaly, LoginEvent
import logging

bp = Blueprint("security", __name__)
logger = logging.getLogger("finmind.security")


@bp.get("/login-history")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    page_size = min(page_size, 200)

    events = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == uid)
        .order_by(LoginEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify(
        [
            {
                "id": e.id,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "success": e.success,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    )


@bp.get("/anomalies")
@jwt_required()
def anomalies():
    uid = int(get_jwt_identity())
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    page_size = min(page_size, 200)

    rows = (
        db.session.query(LoginAnomaly)
        .filter(LoginAnomaly.user_id == uid)
        .order_by(LoginAnomaly.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify(
        [
            {
                "id": a.id,
                "login_event_id": a.login_event_id,
                "anomaly_type": a.anomaly_type,
                "detail": a.detail,
                "acknowledged": a.acknowledged,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ]
    )


@bp.post("/anomalies/<int:anomaly_id>/acknowledge")
@jwt_required()
def acknowledge_anomaly(anomaly_id: int):
    uid = int(get_jwt_identity())
    anomaly = (
        db.session.query(LoginAnomaly)
        .filter(LoginAnomaly.id == anomaly_id, LoginAnomaly.user_id == uid)
        .first()
    )
    if not anomaly:
        return jsonify(error="not found"), 404
    anomaly.acknowledged = True
    db.session.commit()
    logger.info("Anomaly %s acknowledged by user_id=%s", anomaly_id, uid)
    return jsonify(message="acknowledged")
