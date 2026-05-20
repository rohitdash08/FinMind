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
from ..models import AuditLog, LoginEvent, User
from datetime import datetime, timedelta
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
        _record_login_event(
            email=email or "",
            user=None,
            successful=False,
            anomaly_detected=False,
            anomaly_reason=None,
        )
        db.session.commit()
        logger.warning("Login failed for email=%s", email)
        return jsonify(error="invalid credentials"), 401
    anomaly = _detect_login_anomaly(user)
    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    _record_login_event(
        email=user.email,
        user=user,
        successful=True,
        anomaly_detected=anomaly["detected"],
        anomaly_reason=anomaly["reason"],
    )
    if anomaly["detected"]:
        db.session.add(
            AuditLog(
                user_id=user.id,
                action=f"login_anomaly:{anomaly['reason']}",
            )
        )
    db.session.commit()
    logger.info("Login success user_id=%s", user.id)
    return jsonify(
        access_token=access,
        refresh_token=refresh,
        security_alert={
            "suspicious": anomaly["detected"],
            "reason": anomaly["reason"],
        },
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


def _client_ip() -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or None
    return request.remote_addr


def _client_user_agent() -> str | None:
    user_agent = request.headers.get("User-Agent")
    if not user_agent:
        return None
    return user_agent[:500]


def _record_login_event(
    email: str,
    user: User | None,
    successful: bool,
    anomaly_detected: bool,
    anomaly_reason: str | None,
) -> None:
    db.session.add(
        LoginEvent(
            user_id=user.id if user else None,
            email=email,
            ip_address=_client_ip(),
            user_agent=_client_user_agent(),
            successful=successful,
            anomaly_detected=anomaly_detected,
            anomaly_reason=anomaly_reason,
        )
    )


def _detect_login_anomaly(user: User) -> dict[str, str | bool | None]:
    ip_address = _client_ip()
    user_agent = _client_user_agent()
    previous_login = (
        db.session.query(LoginEvent)
        .filter_by(user_id=user.id, successful=True)
        .order_by(LoginEvent.created_at.desc())
        .first()
    )
    if previous_login:
        if ip_address and previous_login.ip_address != ip_address:
            return {"detected": True, "reason": "new_ip_address"}
        if user_agent and previous_login.user_agent != user_agent:
            return {"detected": True, "reason": "new_user_agent"}

    window_start = datetime.utcnow() - timedelta(minutes=15)
    failed_attempts = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.email == user.email,
            LoginEvent.successful.is_(False),
            LoginEvent.created_at >= window_start,
        )
        .count()
    )
    if failed_attempts >= 5:
        return {"detected": True, "reason": "recent_failed_attempts"}
    return {"detected": False, "reason": None}
