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
from ..services.security import (
    detect_unusual_hour,
    get_client_ip,
    get_login_events,
    is_brute_force,
    log_audit_event,
    record_failed_login,
    reset_failure_count,
    store_login_event,
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
    """POST /auth/register – Create a new user account.

    Request body: {email, password}
    Returns:
        201: {message}
        400: Missing required fields
        409: Email already registered
    """
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
    """POST /auth/login – Authenticate and return JWT tokens.

    Includes brute-force protection (Redis failure counters) and unusual-hour
    detection (01:00–04:59 UTC triggers a ``security_alert`` field).

    Request body: {email, password}
    Returns:
        200: {access_token, refresh_token, security_alert?}
        400: Missing required fields
        401: Invalid credentials
        429: Too many failed attempts (brute-force blocked)
    """
    ip = get_client_ip()
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify(error="email and password required"), 400

    # ── Brute-force gate ─────────────────────────────────────────────────────
    if is_brute_force(ip, email):
        log_audit_event(
            action="brute_force_blocked",
            ip=ip,
            details=f"Blocked login attempt for {email}",
        )
        logger.warning("Brute-force blocked ip=%s email=%s", ip, email)
        return jsonify(error="too_many_attempts"), 429

    # ── Credential check ─────────────────────────────────────────────────────
    user = db.session.query(User).filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        failure_count = record_failed_login(ip, email)
        log_audit_event(
            action="login_failed",
            user_id=user.id if user else None,
            ip=ip,
            details=f"Failed attempt #{failure_count} for {email}",
        )
        logger.warning("Login failed for email=%s ip=%s attempt=%s", email, ip, failure_count)
        return jsonify(error="invalid credentials"), 401

    # ── Success ──────────────────────────────────────────────────────────────
    reset_failure_count(ip, email)
    store_login_event(user.id, ip)
    log_audit_event(
        action="login_success",
        user_id=user.id,
        ip=ip,
        details=f"Successful login for {email}",
    )

    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    logger.info("Login success user_id=%s ip=%s", user.id, ip)

    response_data = dict(access_token=access, refresh_token=refresh)

    # Unusual-hour security alert
    alert = detect_unusual_hour()
    if alert:
        response_data["security_alert"] = alert

    return jsonify(response_data)


@bp.get("/me")
@jwt_required()
def me():
    """GET /auth/me – Return the authenticated user's profile."""
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
    """PATCH /auth/me – Update authenticated user's profile."""
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
    """POST /auth/refresh – Issue a new access token from a valid refresh token."""
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
    """POST /auth/logout – Revoke the current refresh token."""
    claims = get_jwt()
    jti = claims.get("jti")
    if jti:
        redis_client.delete(_refresh_key(jti))
    return jsonify(message="logged out"), 200


@bp.get("/security-events")
@jwt_required()
def security_events():
    """GET /auth/security-events – Return the last 10 login events for the user.

    Reads from Redis keys ``auth:login_event:{user_id}:*`` and returns them
    sorted newest-first.

    Returns:
        200: {events: [{ip, hour, timestamp}, ...]}
        401: Missing or invalid JWT
    """
    user_id = int(get_jwt_identity())
    events = get_login_events(user_id, limit=10)
    return jsonify(events=events)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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
