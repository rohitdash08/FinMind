from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta
from ..services.login_anomaly import LoginAnomalyDetector
from ..middleware.auth import require_auth

login_anomaly_bp = Blueprint("login_anomaly", __name__)
detector = LoginAnomalyDetector()

@login_anomaly_bp.route("/api/security/login-events", methods=["GET"])
@require_auth
def get_login_events():
    """Get recent login events for the authenticated user."""
    user_id = g.user_id
    limit = min(int(request.args.get("limit", 20)), 100)
    events = detector.get_login_events(user_id, limit=limit)
    return jsonify({"login_events": events, "count": len(events)})

@login_anomaly_bp.route("/api/security/login-events", methods=["POST"])
@require_auth
def record_login_event():
    """Record a login event and check for anomalies."""
    user_id = g.user_id
    data = request.get_json() or {}
    ip_address = data.get("ip_address") or request.remote_addr
    user_agent = data.get("user_agent") or request.headers.get("User-Agent", "")
    location = data.get("location", {})
    login_time = datetime.utcnow()
    event = {
        "user_id": user_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "location": location,
        "timestamp": login_time.isoformat(),
        "success": data.get("success", True),
    }
    anomalies = detector.analyze_login(event)
    detector.store_login_event(event, anomalies)
    response = {"event_recorded": True, "anomalies": anomalies}
    if anomalies:
        response["alert"] = {
            "level": anomalies[0]["severity"],
            "message": anomalies[0]["description"],
            "action_required": anomalies[0]["severity"] in ("high", "critical"),
        }
    return jsonify(response), 201

@login_anomaly_bp.route("/api/security/alerts", methods=["GET"])
@require_auth
def get_security_alerts():
    """Get unresolved security alerts for the user."""
    user_id = g.user_id
    alerts = detector.get_active_alerts(user_id)
    return jsonify({"alerts": alerts, "count": len(alerts)})

@login_anomaly_bp.route("/api/security/alerts/<alert_id>/dismiss", methods=["POST"])
@require_auth
def dismiss_alert(alert_id):
    """Dismiss a security alert."""
    user_id = g.user_id
    success = detector.dismiss_alert(user_id, alert_id)
    if not success:
        return jsonify({"error": "alert not found"}), 404
    return jsonify({"dismissed": True, "alert_id": alert_id})

@login_anomaly_bp.route("/api/security/trusted-ips", methods=["GET"])
@require_auth
def get_trusted_ips():
    """Get the user list of trusted IPs."""
    user_id = g.user_id
    trusted = detector.get_trusted_ips(user_id)
    return jsonify({"trusted_ips": trusted})

@login_anomaly_bp.route("/api/security/trusted-ips", methods=["POST"])
@require_auth
def add_trusted_ip():
    """Add an IP to the trusted list."""
    user_id = g.user_id
    data = request.get_json() or {}
    ip = data.get("ip_address")
    if not ip:
        return jsonify({"error": "ip_address required"}), 400
    detector.add_trusted_ip(user_id, ip)
    return jsonify({"trusted": True, "ip_address": ip}), 201
