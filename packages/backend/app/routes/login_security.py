"""Login anomaly detection and suspicious activity alerts."""
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import LoginEvent
import logging

bp = Blueprint("login_security", __name__)
logger = logging.getLogger("finmind.login_security")

def _event_to_dict(e):
    return {"id": e.id, "ip_address": e.ip_address, "user_agent": e.user_agent, "success": e.success, "suspicious": e.suspicious, "reason": e.reason, "created_at": e.created_at.isoformat()}

def record_login(user_id, ip, user_agent, success):
    suspicious = False
    reason = None
    if success:
        recent = db.session.query(LoginEvent).filter(
            LoginEvent.user_id == user_id, LoginEvent.success == True,
            LoginEvent.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).all()
        known_ips = {e.ip_address for e in recent}
        if known_ips and ip not in known_ips and len(known_ips) >= 1:
            suspicious = True
            reason = f"New IP address: {ip}"
    else:
        failed_count = db.session.query(LoginEvent).filter(
            LoginEvent.user_id == user_id, LoginEvent.success == False,
            LoginEvent.created_at >= datetime.utcnow() - timedelta(minutes=30)
        ).count()
        if failed_count >= 3:
            suspicious = True
            reason = f"Brute force: {failed_count + 1} failed attempts in 30 min"
    event = LoginEvent(user_id=user_id, ip_address=ip, user_agent=user_agent, success=success, suspicious=suspicious, reason=reason)
    db.session.add(event)
    db.session.commit()
    return event

@bp.get("/history")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    events = db.session.query(LoginEvent).filter_by(user_id=uid).order_by(LoginEvent.created_at.desc()).limit(50).all()
    return jsonify([_event_to_dict(e) for e in events])

@bp.get("/suspicious")
@jwt_required()
def suspicious_logins():
    uid = int(get_jwt_identity())
    events = db.session.query(LoginEvent).filter_by(user_id=uid, suspicious=True).order_by(LoginEvent.created_at.desc()).limit(20).all()
    return jsonify([_event_to_dict(e) for e in events])

@bp.get("/stats")
@jwt_required()
def login_stats():
    uid = int(get_jwt_identity())
    total = db.session.query(LoginEvent).filter_by(user_id=uid).count()
    failed = db.session.query(LoginEvent).filter_by(user_id=uid, success=False).count()
    suspicious = db.session.query(LoginEvent).filter_by(user_id=uid, suspicious=True).count()
    ips = db.session.query(LoginEvent.ip_address).filter_by(user_id=uid, success=True).distinct().count()
    return jsonify(total_logins=total, failed_attempts=failed, suspicious_events=suspicious, unique_ips=ips)
