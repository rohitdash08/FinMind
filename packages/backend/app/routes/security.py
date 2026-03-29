"""Security endpoints for login anomaly detection.

Provides endpoints for users to:
- View their login history
- Manage known devices
- View and acknowledge security alerts
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import desc
from ..extensions import db
from ..models import UserDevice, LoginAttempt, LoginAnomaly, LoginAnomalyType
import logging

bp = Blueprint("security", __name__)
logger = logging.getLogger("finmind.security")


@bp.get("/devices")
@jwt_required()
def list_devices():
    """List all registered devices for the current user."""
    uid = int(get_jwt_identity())
    
    devices = db.session.query(UserDevice).filter(
        UserDevice.user_id == uid
    ).order_by(desc(UserDevice.last_seen)).all()
    
    return jsonify([
        {
            "id": d.id,
            "device_name": d.device_name,
            "device_fingerprint": d.device_fingerprint[:8] + "...",  # Partial fingerprint
            "ip_address": d.ip_address,
            "user_agent": d.user_agent,
            "country": d.country,
            "city": d.city,
            "first_seen": d.first_seen.isoformat() if d.first_seen else None,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "is_trusted": d.is_trusted,
            "is_revoked": d.is_revoked,
        }
        for d in devices
    ])


@bp.patch("/devices/<int:device_id>")
@jwt_required()
def update_device(device_id):
    """Update a device (trust/revoke/rename)."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    device = db.session.query(UserDevice).filter(
        UserDevice.id == device_id,
        UserDevice.user_id == uid
    ).first()
    
    if not device:
        return jsonify(error="device not found"), 404
    
    if "device_name" in data:
        device.device_name = data["device_name"][:200]
    
    if "is_trusted" in data:
        device.is_trusted = bool(data["is_trusted"])
    
    if "is_revoked" in data:
        device.is_revoked = bool(data["is_revoked"])
        if device.is_revoked:
            logger.info(
                "Device revoked: user_id=%s device_id=%s fingerprint=%s",
                uid, device_id, device.device_fingerprint[:8]
            )
    
    db.session.commit()
    
    return jsonify({
        "id": device.id,
        "device_name": device.device_name,
        "is_trusted": device.is_trusted,
        "is_revoked": device.is_revoked,
    })


@bp.delete("/devices/<int:device_id>")
@jwt_required()
def revoke_device(device_id):
    """Revoke a device."""
    uid = int(get_jwt_identity())
    
    device = db.session.query(UserDevice).filter(
        UserDevice.id == device_id,
        UserDevice.user_id == uid
    ).first()
    
    if not device:
        return jsonify(error="device not found"), 404
    
    device.is_revoked = True
    db.session.commit()
    
    logger.info(
        "Device revoked: user_id=%s device_id=%s",
        uid, device_id
    )
    
    return jsonify(message="device revoked"), 200


@bp.get("/login-history")
@jwt_required()
def login_history():
    """Get recent login history for the current user."""
    uid = int(get_jwt_identity())
    
    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 100)  # Cap at 100
    
    attempts = db.session.query(LoginAttempt).filter(
        LoginAttempt.user_id == uid
    ).order_by(desc(LoginAttempt.created_at)).limit(limit).all()
    
    return jsonify([
        {
            "id": a.id,
            "ip_address": a.ip_address,
            "user_agent": a.user_agent,
            "success": a.success,
            "failure_reason": a.failure_reason,
            "country": a.country,
            "city": a.city,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in attempts
    ])


@bp.get("/alerts")
@jwt_required()
def list_alerts():
    """List security alerts for the current user."""
    uid = int(get_jwt_identity())
    
    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 100)
    unacknowledged_only = request.args.get("unacknowledged", "false").lower() == "true"
    
    query = db.session.query(LoginAnomaly).filter(
        LoginAnomaly.user_id == uid
    )
    
    if unacknowledged_only:
        query = query.filter(LoginAnomaly.acknowledged == False)
    
    alerts = query.order_by(desc(LoginAnomaly.created_at)).limit(limit).all()
    
    import json
    return jsonify([
        {
            "id": a.id,
            "anomaly_type": a.anomaly_type.value if a.anomaly_type else None,
            "severity": a.severity,
            "details": json.loads(a.details) if a.details else {},
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ])


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def acknowledge_alert(alert_id):
    """Acknowledge a security alert."""
    uid = int(get_jwt_identity())
    
    alert = db.session.query(LoginAnomaly).filter(
        LoginAnomaly.id == alert_id,
        LoginAnomaly.user_id == uid
    ).first()
    
    if not alert:
        return jsonify(error="alert not found"), 404
    
    alert.acknowledged = True
    db.session.commit()
    
    logger.info(
        "Alert acknowledged: user_id=%s alert_id=%s type=%s",
        uid, alert_id, alert.anomaly_type.value if alert.anomaly_type else None
    )
    
    return jsonify(message="alert acknowledged"), 200


@bp.post("/alerts/acknowledge-all")
@jwt_required()
def acknowledge_all_alerts():
    """Acknowledge all unacknowledged alerts for the current user."""
    uid = int(get_jwt_identity())
    
    updated = db.session.query(LoginAnomaly).filter(
        LoginAnomaly.user_id == uid,
        LoginAnomaly.acknowledged == False
    ).update({"acknowledged": True})
    
    db.session.commit()
    
    logger.info(
        "All alerts acknowledged: user_id=%s count=%s",
        uid, updated
    )
    
    return jsonify(message="all alerts acknowledged", count=updated), 200
