from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.reminder_reliability import get_reliability_metrics, log_delivery_attempt
from ..models import ReminderDeliveryStatus

bp = Blueprint("reminder_reliability", __name__, url_prefix="/reminders/reliability")


@bp.get("/")
@jwt_required()
def reliability_metrics():
    """
    GET /reminders/reliability/
    Query params:
      - days (optional, default 30): number of days to analyse
    Returns delivery reliability stats for the authenticated user.
    """
    user_id = int(get_jwt_identity())
    try:
        days = int(request.args.get("days", 30))
        if days < 1 or days > 365:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "days must be an integer between 1 and 365"}), 400

    metrics = get_reliability_metrics(user_id, days)
    return jsonify(metrics), 200


@bp.post("/log")
@jwt_required()
def log_attempt():
    """
    POST /reminders/reliability/log
    Body: {reminder_id, channel, status, error_message?, latency_ms?}
    Records a delivery attempt for auditing purposes.
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    reminder_id = data.get("reminder_id")
    channel = data.get("channel")
    status_str = data.get("status")

    if not reminder_id or not channel or not status_str:
        return jsonify({"error": "reminder_id, channel, and status are required"}), 400

    try:
        status = ReminderDeliveryStatus(status_str.upper())
    except ValueError:
        valid = [s.value for s in ReminderDeliveryStatus]
        return jsonify({"error": f"status must be one of: {valid}"}), 400

    log = log_delivery_attempt(
        reminder_id=reminder_id,
        user_id=user_id,
        channel=channel,
        status=status,
        error_message=data.get("error_message"),
        latency_ms=data.get("latency_ms"),
    )
    return jsonify({"id": log.id, "status": log.status.value}), 201
