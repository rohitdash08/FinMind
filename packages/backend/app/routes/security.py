"""
Security API Routes

Endpoints for login anomaly detection and security alerts:
- POST /security/record - Record a login event
- GET /security/history - Get login history
- GET /security/alerts - Get security alerts
- POST /security/alerts/<id>/acknowledge - Acknowledge an alert
- POST /security/alerts/acknowledge-all - Acknowledge all alerts
- GET /security/stats - Get security statistics
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.login_anomaly import (
    record_login_event,
    get_user_login_history,
    get_user_alerts,
    acknowledge_alert,
    acknowledge_all_alerts,
    get_security_stats,
    process_login,
    check_brute_force,
    get_client_ip,
    get_user_agent,
    get_device_fingerprint,
    calculate_risk_score,
    LoginEventType,
    AlertSeverity,
)
from ..extensions import db
from ..models import User, SecurityAlert

bp = Blueprint("security", __name__)
logger = logging.getLogger("finmind.security")


@bp.post("/record")
@jwt_required()
def record_event():
    """
    Record a login event with anomaly detection.
    
    Request body:
    - event_type: 'login_success' | 'login_failed' | 'logout'
    - ip_address (optional): Client IP
    - user_agent (optional): Client user agent
    - device_fingerprint (optional): Device fingerprint
    - location_country (optional): Country name
    - location_city (optional): City name
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404
    
    data = request.get_json() or {}
    event_type = data.get("event_type")
    
    if event_type not in [e.value for e in LoginEventType]:
        return jsonify(error=f"invalid event_type. Must be one of: {[e.value for e in LoginEventType]}"), 400
    
    ip_address = data.get("ip_address") or get_client_ip()
    user_agent = data.get("user_agent") or get_user_agent()
    device_fp = data.get("device_fingerprint") or get_device_fingerprint()
    
    # Calculate risk score
    risk_score, risk_factors = calculate_risk_score(
        user_id=uid,
        ip_address=ip_address,
        device_fingerprint=device_fp,
        event_type=event_type
    )
    
    # Record the event
    event = record_login_event(
        user_id=uid,
        event_type=event_type,
        ip_address=ip_address,
        user_agent=user_agent,
        device_fingerprint=device_fp,
        location_country=data.get("location_country"),
        location_city=data.get("location_city"),
        risk_score=risk_score,
        risk_factors=risk_factors
    )
    
    return jsonify({
        "message": "event recorded",
        "event": event.to_dict(),
        "risk_score": risk_score,
        "risk_factors": risk_factors
    }), 201


@bp.get("/history")
@jwt_required()
def login_history():
    """
    Get login history for the current user.
    
    Query params:
    - event_type (optional): Filter by event type
    - limit (optional): Max results (default 50, max 200)
    - offset (optional): Pagination offset
    """
    uid = int(get_jwt_identity())
    
    event_type = request.args.get("event_type")
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify(error="invalid limit or offset"), 400
    
    history = get_user_login_history(
        user_id=uid,
        event_type=event_type,
        limit=limit,
        offset=offset
    )
    
    return jsonify({
        "events": history,
        "count": len(history),
        "limit": limit,
        "offset": offset
    })


@bp.get("/alerts")
@jwt_required()
def alerts():
    """
    Get security alerts for the current user.
    
    Query params:
    - status (optional): Filter by status (active, acknowledged, resolved)
    - severity (optional): Filter by severity (low, medium, high, critical)
    - limit (optional): Max results (default 50, max 200)
    - offset (optional): Pagination offset
    """
    uid = int(get_jwt_identity())
    
    status = request.args.get("status")
    severity = request.args.get("severity")
    
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify(error="invalid limit or offset"), 400
    
    user_alerts = get_user_alerts(
        user_id=uid,
        status=status,
        severity=severity,
        limit=limit,
        offset=offset
    )
    
    return jsonify({
        "alerts": user_alerts,
        "count": len(user_alerts),
        "limit": limit,
        "offset": offset
    })


@bp.post("/alerts/<int:alert_id>/acknowledge")
@jwt_required()
def acknowledge_alert_route(alert_id: int):
    """
    Acknowledge a security alert.
    """
    uid = int(get_jwt_identity())
    
    alert = acknowledge_alert(alert_id=alert_id, user_id=uid)
    
    if not alert:
        return jsonify(error="alert not found"), 404
    
    return jsonify({
        "message": "alert acknowledged",
        "alert": alert.to_dict()
    })


@bp.post("/alerts/acknowledge-all")
@jwt_required()
def acknowledge_all_route():
    """
    Acknowledge all active security alerts for the current user.
    """
    uid = int(get_jwt_identity())
    
    count = acknowledge_all_alerts(user_id=uid)
    
    return jsonify({
        "message": "all alerts acknowledged",
        "count": count
    })


@bp.get("/stats")
@jwt_required()
def stats():
    """
    Get security statistics for the current user.
    
    Query params:
    - days (optional): Number of days to include (default 30, max 365)
    """
    uid = int(get_jwt_identity())
    
    try:
        days = min(int(request.args.get("days", 30)), 365)
    except ValueError:
        return jsonify(error="invalid days parameter"), 400
    
    statistics = get_security_stats(user_id=uid, days=days)
    
    return jsonify(statistics)


@bp.get("/check-ip")
@jwt_required()
def check_ip():
    """
    Check if the current IP is blocked due to brute force.
    """
    ip_address = get_client_ip()
    is_blocked = check_brute_force(ip_address)
    
    return jsonify({
        "ip_address": ip_address,
        "blocked": is_blocked
    })


@bp.post("/analyze")
@jwt_required()
def analyze_login():
    """
    Analyze a potential login and return risk assessment.
    Does not record anything - just returns the analysis.
    
    Request body:
    - ip_address (optional): IP to analyze
    - device_fingerprint (optional): Device fingerprint
    """
    uid = int(get_jwt_identity())
    
    data = request.get_json() or {}
    ip_address = data.get("ip_address") or get_client_ip()
    device_fp = data.get("device_fingerprint") or get_device_fingerprint()
    
    risk_score, risk_factors = calculate_risk_score(
        user_id=uid,
        ip_address=ip_address,
        device_fingerprint=device_fp,
        event_type=LoginEventType.LOGIN_SUCCESS.value
    )
    
    return jsonify({
        "ip_address": ip_address,
        "device_fingerprint": device_fp,
        "risk_score": risk_score,
        "risk_factors": risk_factors,
        "recommendation": "allow" if risk_score < 0.5 else "review" if risk_score < 0.7 else "block"
    })