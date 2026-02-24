"""API routes for reminder delivery metrics (#123)."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.delivery_metrics import (
    log_delivery, get_delivery_metrics, get_delivery_history,
)

bp = Blueprint("delivery_metrics", __name__)


def _serialize(entry):
    return {
        "id": entry.id,
        "reminder_id": entry.reminder_id,
        "channel": entry.channel,
        "status": entry.status,
        "error_message": entry.error_message,
        "sent_at": entry.sent_at.isoformat(),
        "delivered_at": entry.delivered_at.isoformat() if entry.delivered_at else None,
        "latency_ms": entry.latency_ms,
    }


@bp.get("/metrics")
@jwt_required()
def metrics():
    uid = int(get_jwt_identity())
    days = request.args.get("days", 30, type=int)
    return jsonify(get_delivery_metrics(uid, days=days))


@bp.get("/history")
@jwt_required()
def history():
    uid = int(get_jwt_identity())
    reminder_id = request.args.get("reminder_id", type=int)
    limit = request.args.get("limit", 50, type=int)
    items = get_delivery_history(uid, reminder_id=reminder_id, limit=limit)
    return jsonify([_serialize(e) for e in items])


@bp.post("/log")
@jwt_required()
def create_log():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    reminder_id = data.get("reminder_id")
    if not reminder_id:
        return jsonify(error="reminder_id required"), 400
    entry = log_delivery(
        user_id=uid,
        reminder_id=reminder_id,
        channel=data.get("channel", "in_app"),
        status=data.get("status", "SENT"),
        error=data.get("error"),
        latency_ms=data.get("latency_ms"),
    )
    return jsonify(_serialize(entry)), 201
