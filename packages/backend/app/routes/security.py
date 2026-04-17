from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db, redis_client
from ..models import AuditLog
import json
import logging

bp = Blueprint("security", __name__)
logger = logging.getLogger("finmind.security")

# Thresholds
MAX_LOGINS_PER_HOUR = 10
MAX_LOGINS_PER_DAY = 30
GEO_CHANGE_WINDOW_MINUTES = 5
ANOMALY_KEY = "finmind:anomaly:{uid}"


def _record_login_attempt(uid, ip_address, user_agent):
    """Record a login attempt for anomaly detection."""
    now = datetime.utcnow()
    hour_key = f"finmind:logins:{uid}:{now.strftime('%Y%m%d%H')}"
    day_key = f"finmind:logins:{uid}:{now.strftime('%Y%m%d')}"

    try:
        pipe = redis_client.pipeline()
        pipe.incr(hour_key)
        pipe.expire(hour_key, 3600)
        pipe.incr(day_key)
        pipe.expire(day_key, 86400)
        pipe.execute()

        hour_count = int(redis_client.get(hour_key) or 0)
        day_count = int(redis_client.get(day_key) or 0)

        anomalies = []
        if hour_count > MAX_LOGINS_PER_HOUR:
            anomalies.append({
                "type": "rapid_logins_hourly",
                "severity": "high",
                "detail": f"{hour_count} logins in the last hour (threshold: {MAX_LOGINS_PER_HOUR})",
            })
        elif hour_count > MAX_LOGINS_PER_HOUR * 0.7:
            anomalies.append({
                "type": "rapid_logins_hourly",
                "severity": "medium",
                "detail": f"{hour_count} logins in the last hour (approaching threshold)",
            })

        if day_count > MAX_LOGINS_PER_DAY:
            anomalies.append({
                "type": "excessive_logins_daily",
                "severity": "high",
                "detail": f"{day_count} logins today (threshold: {MAX_LOGINS_PER_DAY})",
            })

        return {
            "hour_count": hour_count,
            "day_count": day_count,
            "anomalies": anomalies,
        }
    except Exception as e:
        logger.warning("Login recording failed: %s", e)
        return {"hour_count": 0, "day_count": 0, "anomalies": []}


def _get_recent_anomalies(uid, days=7):
    """Retrieve stored anomalies from audit logs."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    logs = (
        AuditLog.query.filter(
            AuditLog.user_id == uid,
            AuditLog.action.like("SECURITY:%"),
            AuditLog.created_at >= cutoff,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    anomalies = []
    for log in logs:
        try:
            parts = log.action.split(":", 2)
            if len(parts) >= 3:
                anomalies.append({
                    "type": parts[1],
                    "detail": parts[2],
                    "timestamp": log.created_at.isoformat(),
                })
        except:
            pass
    return anomalies


def _log_security_event(uid, event_type, detail):
    """Log a security event to audit trail."""
    entry = AuditLog(
        user_id=uid,
        action=f"SECURITY:{event_type}:{detail}",
    )
    db.session.add(entry)
    db.session.commit()


@bp.route("/login-check", methods=["POST"])
@jwt_required()
def check_login():
    """Check a login attempt for anomalies. Call after successful auth."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    ip = data.get("ip", request.remote_addr or "unknown")
    ua = data.get("user_agent", request.headers.get("User-Agent", "unknown"))

    result = _record_login_attempt(uid, ip, ua)

    if result["anomalies"]:
        for a in result["anomalies"]:
            _log_security_event(uid, a["type"], a["detail"])
            logger.warning("Anomaly detected user=%s type=%s", uid, a["type"])

    return jsonify(result)


@bp.route("/alerts")
@jwt_required()
def get_alerts():
    """Get recent security alerts for the authenticated user."""
    uid = int(get_jwt_identity())
    days = request.args.get("days", 7, type=int)
    anomalies = _get_recent_anomalies(uid, days)

    # Get login stats
    now = datetime.utcnow()
    hour_key = f"finmind:logins:{uid}:{now.strftime('%Y%m%d%H')}"
    day_key = f"finmind:logins:{uid}:{now.strftime('%Y%m%d')}"

    try:
        hour_count = int(redis_client.get(hour_key) or 0)
        day_count = int(redis_client.get(day_key) or 0)
    except:
        hour_count = day_count = 0

    return jsonify({
        "recent_anomalies": anomalies,
        "current_stats": {
            "logins_this_hour": hour_count,
            "logins_today": day_count,
            "hour_threshold": MAX_LOGINS_PER_HOUR,
            "day_threshold": MAX_LOGINS_PER_DAY,
        },
        "thresholds": {
            "max_logins_per_hour": MAX_LOGINS_PER_HOUR,
            "max_logins_per_day": MAX_LOGINS_PER_DAY,
        },
    })


@bp.route("/dismiss/<int:log_id>", methods=["POST"])
@jwt_required()
def dismiss_alert(log_id):
    """Dismiss a security alert."""
    uid = int(get_jwt_identity())
    log = AuditLog.query.filter_by(id=log_id, user_id=uid).first()
    if not log:
        return jsonify(error="Alert not found"), 404
    _log_security_event(uid, "ALERT_DISMISSED", str(log_id))
    return jsonify(status="dismissed")
