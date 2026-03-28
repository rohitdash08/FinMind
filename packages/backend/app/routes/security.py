"""Security routes — login history and anomaly reporting."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import LoginEvent

bp = Blueprint("security", __name__)

_DEFAULT_LIMIT = 50


@bp.get("/login-history")
@jwt_required()
def login_history():
    """Return recent login events for the authenticated user."""
    uid = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", _DEFAULT_LIMIT)), 200)
    events = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == uid)
        .order_by(LoginEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify([_event_to_dict(e) for e in events])


@bp.get("/anomalies")
@jwt_required()
def anomalies():
    """Return only suspicious login events (anomaly_score > 0)."""
    uid = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", _DEFAULT_LIMIT)), 200)
    events = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == uid, LoginEvent.anomaly_score > 0)
        .order_by(LoginEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify([_event_to_dict(e) for e in events])


@bp.get("/login-stats")
@jwt_required()
def login_stats():
    """Aggregate security statistics for the authenticated user."""
    uid = int(get_jwt_identity())

    total = db.session.query(LoginEvent).filter(LoginEvent.user_id == uid).count()
    unique_ips = (
        db.session.query(LoginEvent.ip_address)
        .filter(LoginEvent.user_id == uid)
        .distinct()
        .count()
    )
    unique_devices = (
        db.session.query(LoginEvent.user_agent)
        .filter(LoginEvent.user_id == uid)
        .distinct()
        .count()
    )
    suspicious_count = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == uid, LoginEvent.anomaly_score > 0)
        .count()
    )
    last_anomaly = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == uid, LoginEvent.anomaly_score > 0)
        .order_by(LoginEvent.created_at.desc())
        .first()
    )

    return jsonify(
        {
            "total_logins": total,
            "unique_ips": unique_ips,
            "unique_devices": unique_devices,
            "suspicious_count": suspicious_count,
            "last_anomaly": last_anomaly.created_at.isoformat() if last_anomaly else None,
        }
    )


def _event_to_dict(e: LoginEvent) -> dict:
    return {
        "id": e.id,
        "ip_address": e.ip_address,
        "user_agent": e.user_agent,
        "success": e.success,
        "anomaly_score": float(e.anomaly_score) if e.anomaly_score is not None else 0.0,
        "anomaly_reasons": e.anomaly_reasons,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
