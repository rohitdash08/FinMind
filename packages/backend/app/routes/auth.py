import logging
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from redis.exceptions import RedisError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, redis_client
from ..models import User

bp = Blueprint("auth", __name__)
logger = logging.getLogger("finmind.auth")
FAILED_ATTEMPTS_WINDOW_SECONDS = 15 * 60
FAILED_ATTEMPTS_THRESHOLD = 5
MAX_SECURITY_ALERTS = 50
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
_memory_refresh_sessions: dict[str, tuple[str, int]] = {}
_memory_known_ips: dict[str, set[str]] = {}
_memory_failed_attempts: dict[str, list[int]] = {}
_memory_security_alerts: dict[str, list[dict]] = {}


def reset_runtime_state():
    _memory_refresh_sessions.clear()
    _memory_known_ips.clear()
    _memory_failed_attempts.clear()
    _memory_security_alerts.clear()


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
    normalized_email = _normalize_email(email)
    user = db.session.query(User).filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        if normalized_email:
            _record_failed_attempt(normalized_email)
        logger.warning("Login failed for email=%s", email)
        return jsonify(error="invalid credentials"), 401

    uid = str(user.id)
    ip_address = _request_ip()
    user_agent = request.headers.get("User-Agent", "")
    suspicious_reasons = []

    if _is_new_ip_for_user(uid, ip_address):
        suspicious_reasons.append("NEW_IP_ADDRESS")
    if (
        normalized_email
        and _count_recent_failed_attempts(normalized_email)
        >= FAILED_ATTEMPTS_THRESHOLD
    ):
        suspicious_reasons.append("MULTIPLE_FAILED_ATTEMPTS")

    if suspicious_reasons:
        _store_security_alert(
            uid=uid,
            reason_codes=suspicious_reasons,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    if normalized_email:
        _clear_failed_attempts(normalized_email)
    _remember_known_ip(uid, ip_address)

    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    logger.info("Login success user_id=%s", user.id)
    return jsonify(
        access_token=access,
        refresh_token=refresh,
        suspicious_activity_alert={
            "triggered": bool(suspicious_reasons),
            "reasons": suspicious_reasons,
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
    if not jti or not _refresh_session_exists(jti):
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
        _delete_refresh_session(jti)
    return jsonify(message="logged out"), 200


@bp.get("/security-alerts")
@jwt_required()
def security_alerts():
    uid = str(get_jwt_identity())
    return jsonify(_get_security_alerts(uid))


def _refresh_key(jti: str) -> str:
    return f"auth:refresh:{jti}"


def _known_ips_key(uid: str) -> str:
    return f"auth:known-ips:{uid}"


def _failed_attempts_key(email: str) -> str:
    return f"auth:failed-attempts:{email}"


def _security_alerts_key(uid: str) -> str:
    return f"auth:security-alerts:{uid}"


def _normalize_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def _request_ip() -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _refresh_session_exists(jti: str) -> bool:
    key = _refresh_key(jti)
    try:
        value = redis_client.get(key)
        if value is not None:
            return True
    except RedisError:
        pass
    cached = _memory_refresh_sessions.get(jti)
    if not cached:
        return False
    _, exp = cached
    if exp <= int(time.time()):
        _memory_refresh_sessions.pop(jti, None)
        return False
    return True


def _delete_refresh_session(jti: str):
    key = _refresh_key(jti)
    try:
        redis_client.delete(key)
    except RedisError:
        pass
    _memory_refresh_sessions.pop(jti, None)


def _store_refresh_session(refresh_token: str, uid: str):
    payload = decode_token(refresh_token)
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    exp_int = int(exp)
    ttl = max(int(exp_int - time.time()), 1)
    key = _refresh_key(jti)
    try:
        redis_client.setex(key, ttl, uid)
        return
    except RedisError:
        _memory_refresh_sessions[jti] = (uid, exp_int)


def _is_new_ip_for_user(uid: str, ip_address: str) -> bool:
    key = _known_ips_key(uid)
    known_ips: set[str] = set()
    try:
        known_ips = {ip for ip in redis_client.smembers(key) if ip}
    except RedisError:
        known_ips = _memory_known_ips.get(uid, set())
    if not known_ips:
        return False
    return ip_address not in known_ips


def _remember_known_ip(uid: str, ip_address: str):
    key = _known_ips_key(uid)
    try:
        redis_client.sadd(key, ip_address)
        return
    except RedisError:
        ips = _memory_known_ips.setdefault(uid, set())
        ips.add(ip_address)


def _record_failed_attempt(email: str):
    now_ts = int(time.time())
    min_ts = now_ts - FAILED_ATTEMPTS_WINDOW_SECONDS
    key = _failed_attempts_key(email)
    member = f"{now_ts}:{uuid4().hex}"
    try:
        redis_client.zadd(key, {member: now_ts})
        redis_client.zremrangebyscore(key, "-inf", min_ts)
        return
    except RedisError:
        attempts = _memory_failed_attempts.setdefault(email, [])
        attempts.append(now_ts)
        _memory_failed_attempts[email] = [ts for ts in attempts if ts > min_ts]


def _count_recent_failed_attempts(email: str) -> int:
    now_ts = int(time.time())
    min_ts = now_ts - FAILED_ATTEMPTS_WINDOW_SECONDS
    key = _failed_attempts_key(email)
    try:
        redis_client.zremrangebyscore(key, "-inf", min_ts)
        count = redis_client.zcount(key, min_ts, "+inf")
        return int(count)
    except RedisError:
        attempts = _memory_failed_attempts.get(email, [])
        fresh = [ts for ts in attempts if ts > min_ts]
        _memory_failed_attempts[email] = fresh
        return len(fresh)


def _clear_failed_attempts(email: str):
    key = _failed_attempts_key(email)
    try:
        redis_client.delete(key)
    except RedisError:
        pass
    _memory_failed_attempts.pop(email, None)


def _store_security_alert(
    uid: str, reason_codes: list[str], ip_address: str, user_agent: str
):
    alert = {
        "reason_codes": reason_codes,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    key = _security_alerts_key(uid)
    encoded = json.dumps(alert)
    try:
        redis_client.lpush(key, encoded)
        redis_client.ltrim(key, 0, MAX_SECURITY_ALERTS - 1)
        return
    except RedisError:
        alerts = _memory_security_alerts.setdefault(uid, [])
        alerts.insert(0, alert)
        _memory_security_alerts[uid] = alerts[:MAX_SECURITY_ALERTS]


def _get_security_alerts(uid: str) -> list[dict]:
    key = _security_alerts_key(uid)
    try:
        encoded_alerts = redis_client.lrange(key, 0, MAX_SECURITY_ALERTS - 1)
        decoded: list[dict] = []
        for item in encoded_alerts:
            try:
                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    decoded.append(parsed)
            except (TypeError, json.JSONDecodeError):
                continue
        return decoded
    except RedisError:
        return _memory_security_alerts.get(uid, [])
