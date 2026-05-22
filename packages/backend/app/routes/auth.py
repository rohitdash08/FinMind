from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
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
from ..models import LoginAlert, LoginEvent, User
import logging
import time

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
        _record_login_event(user, email or "", success=False)
        logger.warning("Login failed for email=%s", email)
        return jsonify(error="invalid credentials"), 401
    _record_login_event(user, email or user.email, success=True)
    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    logger.info("Login success user_id=%s", user.id)
    return jsonify(access_token=access, refresh_token=refresh)


@bp.get("/login-history")
@jwt_required()
def login_history():
    uid = int(get_jwt_identity())
    events = (
        db.session.query(LoginEvent)
        .filter_by(user_id=uid)
        .order_by(LoginEvent.created_at.desc())
        .limit(25)
        .all()
    )
    return jsonify(
        events=[
            {
                "id": event.id,
                "ip_address": event.ip_address,
                "user_agent": event.user_agent,
                "success": event.success,
                "is_suspicious": event.is_suspicious,
                "suspicion_reasons": _split_reasons(event.suspicion_reasons),
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]
    )


@bp.get("/alerts")
@jwt_required()
def alerts():
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(LoginAlert)
        .filter_by(user_id=uid)
        .order_by(LoginAlert.created_at.desc())
        .limit(25)
        .all()
    )
    return jsonify(alerts=[_alert_payload(row) for row in rows])


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def acknowledge_alert(alert_id: int):
    uid = int(get_jwt_identity())
    alert = db.session.get(LoginAlert, alert_id)
    if not alert or alert.user_id != uid:
        return jsonify(error="not found"), 404
    alert.acknowledged = True
    db.session.commit()
    return jsonify(_alert_payload(alert))


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


def _record_login_event(user: User | None, email: str, success: bool) -> LoginEvent:
    ip_address = _request_ip()
    user_agent = (request.headers.get("User-Agent") or "unknown")[:500]
    reasons = _detect_login_anomalies(user, ip_address, user_agent, success)
    event = LoginEvent(
        user_id=user.id if user else None,
        email=email[:255],
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        is_suspicious=bool(reasons),
        suspicion_reasons=",".join(reasons) if reasons else None,
    )
    db.session.add(event)
    db.session.flush()
    if user and reasons:
        db.session.add(
            LoginAlert(
                user_id=user.id,
                login_event_id=event.id,
                alert_type="suspicious_login",
                message=_alert_message(reasons),
            )
        )
    db.session.commit()
    return event


def _detect_login_anomalies(
    user: User | None, ip_address: str, user_agent: str, success: bool
) -> list[str]:
    if not user:
        return []

    reasons: list[str] = []
    if success:
        prior_success = (
            db.session.query(LoginEvent)
            .filter_by(user_id=user.id, success=True)
            .first()
        )
        if prior_success:
            seen_ip = (
                db.session.query(LoginEvent.id)
                .filter_by(user_id=user.id, success=True, ip_address=ip_address)
                .first()
            )
            if not seen_ip:
                reasons.append("new_ip")
            seen_device = (
                db.session.query(LoginEvent.id)
                .filter_by(user_id=user.id, success=True, user_agent=user_agent)
                .first()
            )
            if not seen_device:
                reasons.append("new_device")
        current_hour = datetime.utcnow().hour
        if current_hour in {1, 2, 3, 4, 5}:
            reasons.append("unusual_hour")
        return reasons

    window_start = datetime.utcnow() - timedelta(minutes=15)
    failed_count = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user.id,
            LoginEvent.success.is_(False),
            LoginEvent.created_at >= window_start,
        )
        .count()
    )
    if failed_count >= 4:
        reasons.append("failed_login_burst")
    return reasons


def _request_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()[:64]
    return (request.remote_addr or "unknown")[:64]


def _split_reasons(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in value.split(",") if item]


def _alert_message(reasons: list[str]) -> str:
    labels = {
        "new_ip": "a new IP address",
        "new_device": "a new device or browser",
        "unusual_hour": "an unusual login time",
        "failed_login_burst": "multiple failed login attempts",
    }
    readable = [labels.get(reason, reason) for reason in reasons]
    return "Suspicious login activity detected: " + ", ".join(readable)


def _alert_payload(alert: LoginAlert) -> dict:
    return {
        "id": alert.id,
        "login_event_id": alert.login_event_id,
        "alert_type": alert.alert_type,
        "message": alert.message,
        "acknowledged": alert.acknowledged,
        "created_at": alert.created_at.isoformat(),
    }
