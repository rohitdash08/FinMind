from datetime import datetime
import hashlib
import logging
import time

from flask import Blueprint, current_app, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    jwt_required,
    get_jwt_identity,
)
from ..extensions import db, redis_client
from ..models import LoginEvent, SecurityAlert, User

bp = Blueprint("auth", __name__)
logger = logging.getLogger("finmind.auth")
SUPPORTED_CURRENCIES = {
    "USD",
    "INR",
    "EUR",
    "GBP",
    "AED",
    "SGD",
    "AUD",
    "CAD",
    "JPY",
}


@bp.post("/register")
def register():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        logger.warning("Register missing email/password")
        return jsonify(error="email and password required"), 400
    if db.session.query(User).filter_by(email=email).first():
        logger.info("Register email already used: %s", email)
        return jsonify(error="email already used"), 409
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        preferred_currency="INR",
    )
    db.session.add(user)
    db.session.commit()
    logger.info("Registered user id=%s email=%s", user.id, email)
    return jsonify(message="registered"), 201


@bp.post("/login")
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    user = db.session.query(User).filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        logger.warning("Login failed for email=%s", email)
        return jsonify(error="invalid credentials"), 401
    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    security_alert = _record_login_event(user)
    logger.info(
        "Login success user_id=%s suspicious=%s",
        user.id,
        security_alert["suspicious"],
    )
    return jsonify(
        access_token=access,
        refresh_token=refresh,
        security_alert=security_alert,
    )


@bp.get("/me")
@jwt_required()
def me():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404
    return jsonify(
        id=user.id,
        email=user.email,
        preferred_currency=user.preferred_currency or "INR",
    )


@bp.patch("/me")
@jwt_required()
def update_me():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "preferred_currency" in data:
        cur = str(data.get("preferred_currency") or "").upper().strip()
        if cur not in SUPPORTED_CURRENCIES:
            return jsonify(error="unsupported preferred_currency"), 400
        user.preferred_currency = cur
    db.session.commit()
    return jsonify(
        id=user.id,
        email=user.email,
        preferred_currency=user.preferred_currency or "INR",
    )


@bp.get("/security-alerts")
@jwt_required()
def security_alerts():
    uid = int(get_jwt_identity())
    unread_only = str(request.args.get("unread_only", "")).lower() in {
        "1",
        "true",
        "yes",
    }
    query = db.session.query(SecurityAlert).filter_by(user_id=uid)
    if unread_only:
        query = query.filter_by(read=False)
    alerts = query.order_by(SecurityAlert.created_at.desc()).limit(50).all()
    return jsonify([_serialize_security_alert(alert) for alert in alerts])


@bp.patch("/security-alerts/<int:alert_id>/read")
@jwt_required()
def mark_security_alert_read(alert_id: int):
    uid = int(get_jwt_identity())
    alert = db.session.get(SecurityAlert, alert_id)
    if not alert or alert.user_id != uid:
        return jsonify(error="not found"), 404
    alert.read = True
    alert.read_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_serialize_security_alert(alert))


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    jti = claims.get("jti")
    if not jti or not redis_client.get(_refresh_key(jti)):
        logger.warning("Refresh rejected: revoked/unknown token jti=%s", jti)
        return jsonify(error="refresh token revoked"), 401
    uid = get_jwt_identity()
    access = create_access_token(identity=str(uid))
    logger.info("Refreshed token for user_id=%s", uid)
    return jsonify(access_token=access)


@bp.post("/logout")
@jwt_required(refresh=True)
def logout():
    claims = get_jwt()
    jti = claims.get("jti")
    if jti:
        redis_client.delete(_refresh_key(jti))
    return jsonify(message="logged out"), 200


def _record_login_event(user: User) -> dict:
    ip_address = _client_ip()
    user_agent = (request.headers.get("User-Agent") or "unknown").strip() or "unknown"
    ip_hash = _fingerprint(ip_address)
    user_agent_hash = _fingerprint(user_agent)
    prior_events = (
        db.session.query(LoginEvent)
        .filter_by(user_id=user.id)
        .order_by(LoginEvent.created_at.desc())
        .limit(20)
        .all()
    )
    suspicious, reasons = _detect_login_anomaly(
        prior_events,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
    )
    message = _login_alert_message(reasons)

    event = LoginEvent(
        user_id=user.id,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        user_agent=user_agent[:255],
        suspicious=suspicious,
        reason=",".join(reasons) if reasons else None,
    )
    db.session.add(event)

    alert = None
    if suspicious:
        alert = SecurityAlert(
            user_id=user.id,
            alert_type="login_anomaly",
            severity="high" if len(reasons) > 1 else "medium",
            message=message,
            details={
                "reasons": reasons,
                "ip": _mask_ip(ip_address),
                "user_agent": user_agent[:255],
            },
        )
        db.session.add(alert)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to record login security event user_id=%s", user.id)
        return {"suspicious": False, "reasons": []}

    payload = {
        "suspicious": suspicious,
        "reasons": reasons,
    }
    if alert:
        payload.update(
            {
                "alert_id": alert.id,
                "message": alert.message,
                "severity": alert.severity,
            }
        )
    return payload


def _detect_login_anomaly(
    prior_events: list[LoginEvent],
    *,
    ip_hash: str,
    user_agent_hash: str,
) -> tuple[bool, list[str]]:
    if not prior_events:
        return False, []

    reasons: list[str] = []
    known_ips = {event.ip_hash for event in prior_events if event.ip_hash}
    known_user_agents = {
        event.user_agent_hash for event in prior_events if event.user_agent_hash
    }

    if ip_hash not in known_ips:
        reasons.append("new_ip")
    if user_agent_hash not in known_user_agents:
        reasons.append("new_device")

    return bool(reasons), reasons


def _login_alert_message(reasons: list[str]) -> str:
    if "new_ip" in reasons and "new_device" in reasons:
        return "New login from an unrecognized network and device."
    if "new_ip" in reasons:
        return "New login from an unrecognized network."
    if "new_device" in reasons:
        return "New login from an unrecognized device."
    return "Login recorded."


def _client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.headers.get("X-Real-IP") or request.remote_addr or "unknown"


def _fingerprint(value: str) -> str:
    secret = current_app.config.get("JWT_SECRET_KEY", "")
    return hashlib.sha256(f"{secret}:{value}".encode("utf-8")).hexdigest()


def _mask_ip(ip_address: str) -> str:
    parts = ip_address.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        return ".".join([parts[0], parts[1], parts[2], "x"])
    if ":" in ip_address:
        return ":".join(ip_address.split(":")[:4]) + "::"
    return "unknown"


def _serialize_security_alert(alert: SecurityAlert) -> dict:
    return {
        "id": alert.id,
        "type": alert.alert_type,
        "severity": alert.severity,
        "message": alert.message,
        "details": alert.details or {},
        "read": alert.read,
        "read_at": alert.read_at.isoformat() if alert.read_at else None,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


def _refresh_key(jti: str) -> str:
    return f"auth:refresh:{jti}"


def _store_refresh_session(refresh_token: str, uid: str):
    payload = decode_token(refresh_token)
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    ttl = max(int(exp - time.time()), 1)
    redis_client.setex(_refresh_key(jti), ttl, uid)
