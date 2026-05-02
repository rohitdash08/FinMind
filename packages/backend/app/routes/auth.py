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
from ..services.locale import get_formatter, LocaleFormatter
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

SUPPORTED_TIMEZONES = {
    "UTC",
    "Asia/Kolkata",
    "America/New_York",
    "America/Los_Angeles",
    "America/Chicago",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Asia/Dubai",
    "Australia/Sydney",
    "Pacific/Auckland",
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
        preferred_locale=user.preferred_locale or "en-US",
        preferred_timezone=user.preferred_timezone or "UTC",
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
    if "preferred_locale" in data:
        loc = str(data.get("preferred_locale") or "").strip()
        if loc not in LocaleFormatter.SUPPORTED_LOCALES:
            return jsonify(error="unsupported preferred_locale"), 400
        user.preferred_locale = loc
    if "preferred_timezone" in data:
        tz = str(data.get("preferred_timezone") or "").strip()
        if tz not in SUPPORTED_TIMEZONES:
            return jsonify(error="unsupported preferred_timezone"), 400
        user.preferred_timezone = tz
    db.session.commit()
    return jsonify(
        id=user.id,
        email=user.email,
        preferred_currency=user.preferred_currency or "INR",
        preferred_locale=user.preferred_locale or "en-US",
        preferred_timezone=user.preferred_timezone or "UTC",
    )


@bp.get("/locale")
@jwt_required()
def get_locale():
    """Get locale formatting info for the current user."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404
    formatter = get_formatter(
        getattr(user, "preferred_locale", None),
        user.preferred_currency,
    )
    return jsonify(formatter.to_dict())


@bp.get("/locale/options")
@jwt_required()
def get_locale_options():
    """Get supported locale, currency, and timezone options."""
    return jsonify(
        locales=LocaleFormatter.SUPPORTED_LOCALES,
        currencies=sorted(LocaleFormatter.CURRENCY_SYMBOLS.keys()),
        timezones=sorted(SUPPORTED_TIMEZONES),
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
