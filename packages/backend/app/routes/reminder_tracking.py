"""Routes for reminder reliability tracking and delivery metrics."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.reminder_tracking import (
    record_delivery_attempt,
    mark_sent,
    mark_delivered,
    mark_failed,
    mark_bounced,
    record_opened,
    record_clicked,
    get_delivery_history,
    get_reminder_deliveries,
    get_reliability_metrics,
    get_channel_performance,
)

bp = Blueprint("reminder_tracking", __name__)


@bp.route("/record", methods=["POST"])
@jwt_required()
def record_attempt():
    """Record a delivery attempt.

    JSON body:
    - reminder_id: int (required)
    - channel: email | push | sms | in_app (default: email)
    - status: pending | sent (default: pending)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    reminder_id = data.get("reminder_id")
    if not reminder_id:
        return jsonify({"error": "reminder_id is required"}), 400

    result = record_delivery_attempt(
        reminder_id=reminder_id,
        user_id=user_id,
        channel=data.get("channel", "email"),
        status=data.get("status", "pending"),
    )

    return jsonify(result), 201


@bp.route("/<int:delivery_id>/sent", methods=["POST"])
@jwt_required()
def sent(delivery_id):
    """Mark delivery as sent.

    JSON body:
    - response_code: server response code (optional)
    """
    data = request.get_json(silent=True) or {}
    result = mark_sent(delivery_id, data.get("response_code", "200"))

    if result is None:
        return jsonify({"error": "Delivery not found"}), 404

    return jsonify(result), 200


@bp.route("/<int:delivery_id>/delivered", methods=["POST"])
@jwt_required()
def delivered(delivery_id):
    """Mark delivery as delivered.

    JSON body:
    - latency_ms: delivery latency in ms (optional)
    """
    data = request.get_json(silent=True) or {}
    result = mark_delivered(delivery_id, data.get("latency_ms", 0))

    if result is None:
        return jsonify({"error": "Delivery not found"}), 404

    return jsonify(result), 200


@bp.route("/<int:delivery_id>/failed", methods=["POST"])
@jwt_required()
def failed(delivery_id):
    """Mark delivery as failed.

    JSON body:
    - reason: failure reason
    - response_code: server response code
    """
    data = request.get_json(silent=True) or {}
    result = mark_failed(
        delivery_id,
        reason=data.get("reason", ""),
        response_code=data.get("response_code", ""),
    )

    if result is None:
        return jsonify({"error": "Delivery not found"}), 404

    return jsonify(result), 200


@bp.route("/<int:delivery_id>/bounced", methods=["POST"])
@jwt_required()
def bounced(delivery_id):
    """Mark delivery as bounced.

    JSON body:
    - reason: bounce reason
    """
    data = request.get_json(silent=True) or {}
    result = mark_bounced(delivery_id, data.get("reason", ""))

    if result is None:
        return jsonify({"error": "Delivery not found"}), 404

    return jsonify(result), 200


@bp.route("/<int:delivery_id>/opened", methods=["POST"])
@jwt_required()
def opened(delivery_id):
    """Record that delivery was opened."""
    result = record_opened(delivery_id)

    if result is None:
        return jsonify({"error": "Delivery not found"}), 404

    return jsonify(result), 200


@bp.route("/<int:delivery_id>/clicked", methods=["POST"])
@jwt_required()
def clicked(delivery_id):
    """Record that delivery link was clicked."""
    result = record_clicked(delivery_id)

    if result is None:
        return jsonify({"error": "Delivery not found"}), 404

    return jsonify(result), 200


@bp.route("/history", methods=["GET"])
@jwt_required()
def delivery_history():
    """Get delivery history.

    Query params:
    - limit: max records (default 50)
    - channel: filter by channel
    - status: filter by status
    """
    user_id = int(get_jwt_identity())
    limit = request.args.get("limit", 50, type=int)
    channel = request.args.get("channel")
    status = request.args.get("status")

    deliveries = get_delivery_history(user_id, limit, channel, status)
    return jsonify({"deliveries": deliveries, "count": len(deliveries)}), 200


@bp.route("/reminder/<int:reminder_id>", methods=["GET"])
@jwt_required()
def reminder_deliveries(reminder_id):
    """Get all delivery attempts for a reminder."""
    deliveries = get_reminder_deliveries(reminder_id)
    return jsonify({"deliveries": deliveries, "count": len(deliveries)}), 200


@bp.route("/metrics", methods=["GET"])
@jwt_required()
def reliability_metrics():
    """Get reliability metrics.

    Query params:
    - days: lookback period (default 30)
    """
    user_id = int(get_jwt_identity())
    days = request.args.get("days", 30, type=int)

    metrics = get_reliability_metrics(user_id, days)
    return jsonify(metrics), 200


@bp.route("/channels", methods=["GET"])
@jwt_required()
def channel_perf():
    """Get channel performance breakdown.

    Query params:
    - days: lookback period (default 30)
    """
    user_id = int(get_jwt_identity())
    days = request.args.get("days", 30, type=int)

    performance = get_channel_performance(user_id, days)
    return jsonify({"channels": performance}), 200
