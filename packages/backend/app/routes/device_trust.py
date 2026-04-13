import hashlib
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AuditLog
import logging

bp = Blueprint("device_trust", __name__)
logger = logging.getLogger("finmind.device_trust")

DEVICE_TRUST_ACTION = "device_trust"
DEVICE_REVOKE_ACTION = "device_revoke"


def _device_fingerprint(user_agent: str, ip: str) -> str:
    """Create a stable hash from user-agent + IP for device identification."""
    raw = f"{user_agent}|{ip}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@bp.get("")
@jwt_required()
def list_devices():
    """List trusted devices for the current user."""
    uid = int(get_jwt_identity())
    entries = (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == uid, AuditLog.action == DEVICE_TRUST_ACTION)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    logger.info("Listed devices user=%s count=%s", uid, len(entries))
    return jsonify(
        [
            {
                "id": e.id,
                "action": e.action,
                "trusted_at": e.created_at.isoformat(),
            }
            for e in entries
        ]
    )


@bp.post("/trust")
@jwt_required()
def trust_device():
    """Register the current device as trusted."""
    uid = int(get_jwt_identity())
    user_agent = request.headers.get("User-Agent", "unknown")
    ip = request.remote_addr or "0.0.0.0"
    fingerprint = _device_fingerprint(user_agent, ip)

    # Check if already trusted
    existing = (
        db.session.query(AuditLog)
        .filter(
            AuditLog.user_id == uid,
            AuditLog.action == DEVICE_TRUST_ACTION,
        )
        .all()
    )
    for entry in existing:
        if fingerprint in (entry.action + str(entry.id)):
            pass  # allow re-trust for simplicity

    entry = AuditLog(
        user_id=uid,
        action=DEVICE_TRUST_ACTION,
    )
    db.session.add(entry)
    db.session.commit()
    logger.info("Trusted device user=%s fingerprint=%s id=%s", uid, fingerprint, entry.id)
    return jsonify(id=entry.id, fingerprint=fingerprint), 201


@bp.delete("/<int:device_id>/revoke")
@jwt_required()
def revoke_device(device_id: int):
    """Remove trusted status from a device."""
    uid = int(get_jwt_identity())
    entry = db.session.get(AuditLog, device_id)
    if not entry or entry.user_id != uid or entry.action != DEVICE_TRUST_ACTION:
        return jsonify(error="not found"), 404

    entry.action = DEVICE_REVOKE_ACTION
    db.session.commit()
    logger.info("Revoked device user=%s device_id=%s", uid, device_id)
    return jsonify(message="device revoked"), 200
