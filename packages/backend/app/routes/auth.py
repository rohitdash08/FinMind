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
    process_login,
    check_brute_force,
    get_client_ip,
    LoginEventType,
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


@bp.post("/login")
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    
    # Get client info for anomaly detection
    ip_address = get_client_ip()
    
    # Check brute force before processing
    if check_brute_force(ip_address):
        logger.warning("Login blocked due to brute force: email=%s, ip=%s", email, ip_address)
        return jsonify(error="too many failed attempts, please try again later"), 429
    
    user = db.session.query(User).filter_by(email=email).first()
    
    # Determine if login is successful
    is_successful = user is not None and check_password_hash(user.password_hash, password)
    
    # Process login with anomaly detection
    login_event, security_alert, should_block = process_login(
        user=user,
        is_successful=is_successful,
        ip_address=ip_address
    )
    
    if should_block:
        logger.warning("Login blocked after brute force detection: email=%s", email)
        return jsonify(error="account temporarily locked due to suspicious activity"), 429
    
    if not is_successful:
        logger.warning("Login failed for email=%s", email)
        return jsonify(error="invalid credentials"), 401
    
    # Successful login - create tokens
    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    
    logger.info("Login success user_id=%s", user.id)
    
    # Build response with security info
    response_data = {
        "access_token": access,
        "refresh_token": refresh,
    }
    
    # Include security alert if generated
    if security_alert:
        response_data["security_alert"] = {
            "type": security_alert.alert_type,
            "severity": security_alert.severity,
            "message": security_alert.title,
        }
        logger.info("Security alert generated for user_id=%s: %s", user.id, security_alert.title)
    
    # Include risk info if elevated
    if login_event and float(login_event.risk_score) > 0.3:
        response_data["security_notice"] = {
            "risk_score": float(login_event.risk_score),
            "message": "Login from new device or location detected"
        }
    
    return jsonify(response_data)


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
