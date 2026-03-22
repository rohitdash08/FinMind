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
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    user_agent = request.headers.get("User-Agent")

    user = db.session.query(User).filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        # Record failed login attempt for anomaly detection
        if user:
            from ..services.login_anomaly import analyse_login
            analyse_login(
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
            )
            db.session.commit()
        logger.warning("Login failed for email=%s", email)
        return jsonify(error="invalid credentials"), 401

    # Analyse login for anomalies
    from ..services.login_anomaly import analyse_login
    score, reasons, _event = analyse_login(
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
    )

    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    db.session.commit()
    logger.info("Login success user_id=%s anomaly_score=%.2f", user.id, score)

    resp = {"access_token": access, "refresh_token": refresh}
    if reasons:
        resp["security_warnings"] = reasons
    return jsonify(resp)


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


@bp.get("/login-history")
@jwt_required()
def login_history():
    """Return the authenticated user's recent login events."""
    uid = int(get_jwt_identity())
    from ..services.login_anomaly import get_login_history
    import json as _json

    events = get_login_history(uid)
    return jsonify(
        [
            {
                "id": e.id,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "country": e.country,
                "city": e.city,
                "success": e.success,
                "anomaly_score": e.anomaly_score,
                "anomaly_reasons": _json.loads(e.anomaly_reasons)
                if e.anomaly_reasons
                else [],
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    )


@bp.get("/alerts")
@jwt_required()
def alerts():
    """Return the authenticated user's security alerts."""
    uid = int(get_jwt_identity())
    from ..services.login_anomaly import get_user_alerts

    unack = request.args.get("unacknowledged", "").lower() in ("1", "true", "yes")
    items = get_user_alerts(uid, unacknowledged_only=unack)
    return jsonify(
        [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "message": a.message,
                "acknowledged": a.acknowledged,
                "created_at": a.created_at.isoformat(),
            }
            for a in items
        ]
    )


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def acknowledge(alert_id: int):
    """Acknowledge a security alert."""
    uid = int(get_jwt_identity())
    from ..services.login_anomaly import acknowledge_alert

    alert = acknowledge_alert(alert_id, uid)
    if not alert:
        return jsonify(error="alert not found"), 404
    db.session.commit()
    return jsonify(message="acknowledged")


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
