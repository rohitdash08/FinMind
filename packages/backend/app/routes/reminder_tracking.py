import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.reminder_tracking import (
    get_delivery_metrics,
    list_deliveries,
    record_click,
    retry_failed_deliveries,
    send_with_tracking,
)
from ..models import Reminder
from ..extensions import db

bp = Blueprint("reminder_tracking", __name__)
logger = logging.getLogger("finmind.reminder_tracking")


@bp.get("/delivery-metrics")
@jwt_required()
def delivery_metrics():
    uid = int(get_jwt_identity())
    metrics = get_delivery_metrics(uid)
    logger.info("Delivery metrics user=%s total=%s", uid, metrics["total"])
    return jsonify(metrics)


@bp.get("/deliveries")
@jwt_required()
def list_delivery_history():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 50, type=int)
    deliveries = list_deliveries(uid, limit=min(limit, 200))
    return jsonify(deliveries)


@bp.post("/deliveries/<int:reminder_id>/click")
@jwt_required()
def track_click(reminder_id: int):
    uid = int(get_jwt_identity())
    if not record_click(reminder_id, uid):
        return jsonify(error="not found"), 404
    return jsonify(message="clicked"), 200


@bp.post("/retry-failed")
@jwt_required()
def retry_failed():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 10, type=int)
    retried = retry_failed_deliveries(uid, limit=min(limit, 50))
    return jsonify(retried=retried)


@bp.post("/send/<int:reminder_id>")
@jwt_required()
def send_single(reminder_id: int):
    uid = int(get_jwt_identity())
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder or reminder.user_id != uid:
        return jsonify(error="not found"), 404
    delivery = send_with_tracking(reminder)
    return jsonify(
        id=delivery.id,
        status=delivery.status.value if delivery.status else "PENDING",
        attempt_count=delivery.attempt_count,
    ), 200
