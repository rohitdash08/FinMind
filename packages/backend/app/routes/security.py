"""Security routes for login anomaly alerts."""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..services.anomaly_detection import SecurityAlert, LoginActivity, TrustedDevice

bp = Blueprint("security", __name__)


@bp.get("/alerts")
@jwt_required()
def get_alerts():
    """Return security alerts for the authenticated user."""
    user_id = int(get_jwt_identity())
    alerts = (
        SecurityAlert.query.filter_by(user_id=user_id)
        .order_by(SecurityAlert.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(
        alerts=[
            {
                "id": a.id,
                "type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "is_read": a.is_read,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]
    )


@bp.patch("/alerts/<int:alert_id>/read")
@jwt_required()
def mark_alert_read(alert_id: int):
    """Mark a security alert as read."""
    user_id = int(get_jwt_identity())
    alert = SecurityAlert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        return jsonify(error="alert not found"), 404
    alert.is_read = True
    db.session.commit()
    return jsonify(message="marked as read")


@bp.get("/login-history")
@jwt_required()
def get_login_history():
    """Return recent login activity for the authenticated user."""
    user_id = int(get_jwt_identity())
    activities = (
        LoginActivity.query.filter_by(user_id=user_id)
        .order_by(LoginActivity.created_at.desc())
        .limit(20)
        .all()
    )
    return jsonify(
        activities=[
            {
                "id": a.id,
                "ip_address": a.ip_address,
                "user_agent": a.user_agent,
                "success": a.success,
                "anomaly_score": a.anomaly_score,
                "anomaly_reasons": a.anomaly_reasons.split(",") if a.anomaly_reasons else [],
                "created_at": a.created_at.isoformat(),
            }
            for a in activities
        ]
    )


@bp.get("/trusted-devices")
@jwt_required()
def get_trusted_devices():
    """Return trusted devices for the authenticated user."""
    user_id = int(get_jwt_identity())
    devices = (
        TrustedDevice.query.filter_by(user_id=user_id, is_trusted=True)
        .order_by(TrustedDevice.last_seen.desc())
        .all()
    )
    return jsonify(
        devices=[
            {
                "id": d.id,
                "device_fingerprint": d.device_fingerprint,
                "user_agent": d.user_agent,
                "ip_address": d.ip_address,
                "first_seen": d.first_seen.isoformat(),
                "last_seen": d.last_seen.isoformat(),
            }
            for d in devices
        ]
    )


@bp.delete("/trusted-devices/<int:device_id>")
@jwt_required()
def revoke_device(device_id: int):
    """Revoke trust from a device."""
    user_id = int(get_jwt_identity())
    device = TrustedDevice.query.filter_by(id=device_id, user_id=user_id).first()
    if not device:
        return jsonify(error="device not found"), 404
    device.is_trusted = False
    db.session.commit()
    return jsonify(message="device trust revoked")
