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
from ..models import User
from ..services.login_anomaly import (
    record_login_attempt,
    is_account_locked,
    get_lockout_remaining,
    get_user_anomalies,
    resolve_anomaly,
    get_login_history,
    get_security_summary,
    clear_account_lockout,
)
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


def _get_client_ip() -> str:
    """Get client IP address from request headers."""
    # Check X-Forwarded-For for proxied requests
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _get_user_agent() -> str:
    """Get user agent from request headers."""
    return request.headers.get("User-Agent", "unknown")[:500]


@bp.post("/login")
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    ip_address = _get_client_ip()
    user_agent = _get_user_agent()
    
    user = db.session.query(User).filter_by(email=email).first()
    
    # Check if account is locked
    if user and is_account_locked(user.id):
        remaining = get_lockout_remaining(user.id)
        logger.warning("Login blocked - account locked for user_id=%s", user.id)
        record_login_attempt(user.id, email, ip_address, user_agent, success=False)
        return jsonify(
            error="account temporarily locked",
            lockout_remaining_seconds=remaining,
        ), 423  # HTTP 423 Locked
    
    if not user or not check_password_hash(user.password_hash, password):
        logger.warning("Login failed for email=%s", email)
        # Record failed attempt
        record_login_attempt(
            user_id=user.id if user else None,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
        )
        return jsonify(error="invalid credentials"), 401
    
    # Record successful login and check for anomalies
    record_login_attempt(
        user_id=user.id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
    )
    
    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    logger.info("Login success user_id=%s", user.id)
    
    # Check for unresolved anomalies to warn user
    anomalies = get_user_anomalies(user.id, unresolved_only=True, limit=5)
    response = {"access_token": access, "refresh_token": refresh}
    
    if anomalies:
        response["security_warnings"] = [
            {
                "id": a.id,
                "type": a.anomaly_type.value,
                "severity": a.severity.value,
                "description": a.description,
                "created_at": a.created_at.isoformat(),
            }
            for a in anomalies
        ]
    
    return jsonify(response)


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


@bp.get("/security/summary")
@jwt_required()
def security_summary():
    """Get security summary for the authenticated user."""
    uid = int(get_jwt_identity())
    summary = get_security_summary(uid)
    return jsonify(summary)


@bp.get("/security/login-history")
@jwt_required()
def login_history():
    """Get login history for the authenticated user."""
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 50, type=int)
    limit = min(limit, 100)  # Cap at 100
    
    history = get_login_history(uid, limit=limit)
    return jsonify(
        login_history=[
            {
                "id": h.id,
                "ip_address": h.ip_address,
                "user_agent": h.user_agent,
                "location": h.location,
                "success": h.success,
                "created_at": h.created_at.isoformat(),
            }
            for h in history
        ]
    )


@bp.get("/security/anomalies")
@jwt_required()
def list_anomalies():
    """Get login anomalies for the authenticated user."""
    uid = int(get_jwt_identity())
    unresolved_only = request.args.get("unresolved", "false").lower() == "true"
    limit = request.args.get("limit", 50, type=int)
    limit = min(limit, 100)  # Cap at 100
    
    anomalies = get_user_anomalies(uid, unresolved_only=unresolved_only, limit=limit)
    return jsonify(
        anomalies=[
            {
                "id": a.id,
                "type": a.anomaly_type.value,
                "severity": a.severity.value,
                "description": a.description,
                "resolved": a.resolved,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in anomalies
        ]
    )


@bp.post("/security/anomalies/<int:anomaly_id>/resolve")
@jwt_required()
def resolve_anomaly_route(anomaly_id: int):
    """Mark an anomaly as resolved (user acknowledges the activity was legitimate)."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    note = data.get("note")
    
    success = resolve_anomaly(anomaly_id, uid, resolution_note=note)
    if not success:
        return jsonify(error="anomaly not found"), 404
    
    return jsonify(message="anomaly resolved")


@bp.post("/security/unlock")
@jwt_required()
def unlock_account():
    """Self-service account unlock after lockout.
    
    Requires valid authentication, which proves the user knows their password.
    This allows legitimate users to unlock their account after a lockout.
    """
    uid = int(get_jwt_identity())
    
    if not is_account_locked(uid):
        return jsonify(message="account is not locked"), 200
    
    clear_account_lockout(uid)
    logger.info("User self-unlocked account: user_id=%s", uid)
    return jsonify(message="account unlocked")


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
