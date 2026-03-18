from flask import Blueprint, request, jsonify, current_app
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
from ..models import User, LoginHistory, SecurityAlert
import logging
import time
from datetime import datetime, timedelta
import resend

def _send_admin_alert(alert_type: str, description: str, user_email: str):
    api_key = current_app.config.get("RESEND_API_KEY")
    admin_email = current_app.config.get("ADMIN_EMAIL")
    email_from = current_app.config.get("EMAIL_FROM") or "security@finmind.com"

    if not api_key or not admin_email:
        logger.warning("Admin alert not sent for %s: RESEND_API_KEY or ADMIN_EMAIL missing.", alert_type)
        return

    resend.api_key = api_key
    try:
        resend.Emails.send({
            "from": email_from,
            "to": admin_email,
            "subject": f"Security Alert: {alert_type} Detected",
            "html": f"<p><strong>Alert Type:</strong> {alert_type}</p><p><strong>User:</strong> {user_email}</p><p><strong>Description:</strong> {description}</p>"
        })
        logger.info("Admin email alert sent for %s", alert_type)
    except Exception as e:
        logger.error("Failed to send admin alert email: %s", e)

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

    if not email or not password:
        return jsonify(error="email and password required"), 400

    ip_address = (
        request.headers.get("X-Forwarded-For", request.remote_addr) or "127.0.0.1"
    )
    ip_address = ip_address.split(",")[0].strip()[:45]
    user_agent = request.user_agent.string if request.user_agent else "Unknown"
    user_agent = user_agent[:500]

    rate_limit_key = f"auth:failed_login:{email}"
    failed_attempts = redis_client.get(rate_limit_key)

    if failed_attempts and int(failed_attempts) >= 5:
        user = db.session.query(User).filter_by(email=email).first()
        if user:
            logger.warning("Brute force attempt blocked for user_id=%s", user.id)
            recent_alert = (
                db.session.query(SecurityAlert)
                .filter(
                    SecurityAlert.user_id == user.id,
                    SecurityAlert.alert_type == "BRUTE_FORCE",
                    SecurityAlert.created_at >= datetime.utcnow() - timedelta(hours=1),
                )
                .first()
            )
            if not recent_alert:
                alert = SecurityAlert(
                    user_id=user.id,
                    alert_type="BRUTE_FORCE",
                    description="Multiple failed login attempts detected in a short time.",
                )
                db.session.add(alert)
                db.session.commit()
                _send_admin_alert("BRUTE_FORCE", alert.description, email)
        return (
            jsonify(error="Too many failed login attempts. Please try again later."),
            429,
        )

    user = db.session.query(User).filter_by(email=email).first()

    if not user or not check_password_hash(user.password_hash, password):
        redis_client.incr(rate_limit_key)
        ttl = redis_client.ttl(rate_limit_key)
        if ttl == -1 or ttl == -2:
            redis_client.expire(rate_limit_key, 900)

        logger.warning("Login failed for email=%s", email)
        history = LoginHistory(
            user_id=user.id if user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            status="FAILED",
        )
        db.session.add(history)
        db.session.commit()
        return jsonify(error="invalid credentials"), 401

    redis_client.delete(rate_limit_key)

    past_success = (
        db.session.query(LoginHistory)
        .filter(
            LoginHistory.user_id == user.id,
            LoginHistory.status == "SUCCESS",
            LoginHistory.ip_address == ip_address,
        )
        .first()
    )

    if not past_success:
        alert = SecurityAlert(
            user_id=user.id,
            alert_type="NEW_DEVICE_LOGIN",
            description=f"Login detected from a new IP address: {ip_address}",
        )
        db.session.add(alert)
        _send_admin_alert("NEW_DEVICE_LOGIN", alert.description, email)

    history = LoginHistory(
        user_id=user.id, ip_address=ip_address, user_agent=user_agent, status="SUCCESS"
    )
    db.session.add(history)
    db.session.commit()

    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    logger.info("Login success user_id=%s", user.id)
    return jsonify(access_token=access, refresh_token=refresh)


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


@bp.get("/alerts")
@jwt_required()
def get_alerts():
    uid = int(get_jwt_identity())
    alerts = (
        db.session.query(SecurityAlert)
        .filter_by(user_id=uid)
        .order_by(SecurityAlert.created_at.desc())
        .limit(10)
        .all()
    )
    return jsonify(
        {
            "alerts": [
                {
                    "id": a.id,
                    "alert_type": a.alert_type,
                    "description": a.description,
                    "is_read": a.is_read,
                    "created_at": a.created_at.isoformat(),
                }
                for a in alerts
            ]
        }
    )


@bp.patch("/alerts/<int:alert_id>/read")
@jwt_required()
def mark_alert_read(alert_id):
    uid = int(get_jwt_identity())
    alert = db.session.get(SecurityAlert, alert_id)
    if not alert or alert.user_id != uid:
        return jsonify(error="not found"), 404
    alert.is_read = True
    db.session.commit()
    return jsonify(message="marked as read")
