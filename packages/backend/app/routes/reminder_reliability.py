"""
Routes for Reminder Reliability Tracking & Delivery Metrics (Issue #123)
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.reminder_reliability import ReminderReliabilityService

bp = Blueprint("reminder_reliability", __name__)
_svc = ReminderReliabilityService()


@bp.get("/metrics")
@jwt_required()
def get_delivery_metrics():
    """GET /reminders/metrics?days=30&channel=email"""
    uid = int(get_jwt_identity())
    days = min(int(request.args.get("days", 30)), 365)
    channel = request.args.get("channel")
    return jsonify(_svc.get_delivery_metrics(uid, days=days, channel=channel))


@bp.get("/metrics/<int:reminder_id>")
@jwt_required()
def get_reminder_metrics(reminder_id: int):
    """GET /reminders/metrics/<id> - per-reminder reliability"""
    uid = int(get_jwt_identity())
    result = _svc.get_reminder_metrics(uid, reminder_id)
    if result.get("error") == "not_found":
        return jsonify(error="Reminder not found"), 404
    return jsonify(result)


@bp.get("/failed")
@jwt_required()
def get_failed_reminders():
    """GET /reminders/failed - list reminders with delivery failures"""
    uid = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify(_svc.get_failed_reminders(uid, limit=limit))


@bp.post("/<int:reminder_id>/delivery-log")
@jwt_required()
def record_delivery(reminder_id: int):
    """POST /reminders/<id>/delivery-log - record a delivery attempt"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    status = data.get("status", "delivered")
    if status not in ("delivered", "failed", "pending"):
        return jsonify(error="status must be delivered|failed|pending"), 400
    log = _svc.record_delivery_attempt(
        user_id=uid,
        reminder_id=reminder_id,
        channel=data.get("channel", "email"),
        status=status,
        latency_ms=data.get("latency_ms"),
        error_code=data.get("error_code"),
        retry_count=data.get("retry_count", 0),
    )
    return jsonify(id=log.id, status=log.status), 201
