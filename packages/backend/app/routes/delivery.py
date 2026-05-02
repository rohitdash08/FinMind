import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.delivery import delivery_tracker

bp = Blueprint("delivery", __name__)
logger = logging.getLogger("finmind.delivery")


@bp.get("/stats")
@jwt_required()
def delivery_stats():
  uid = int(get_jwt_identity())
  days = request.args.get("days", 30, type=int)
  stats = delivery_tracker.get_delivery_stats(user_id=uid, days=days)
  logger.info("Delivery stats user=%s days=%s", uid, days)
  return jsonify(stats)


@bp.get("/stats/channels")
@jwt_required()
def channel_stats():
  uid = int(get_jwt_identity())
  days = request.args.get("days", 30, type=int)
  stats = delivery_tracker.get_channel_stats(days=days)
  logger.info("Channel stats user=%s days=%s", uid, days)
  return jsonify(stats)


@bp.get("/history")
@jwt_required()
def delivery_history():
  uid = int(get_jwt_identity())
  page = max(int(request.args.get("page", 1)), 1)
  page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)

  items, total = delivery_tracker.get_delivery_history(
    user_id=uid,
    page=page,
    page_size=page_size,
  )
  logger.info("Delivery history user=%s count=%s", uid, total)
  return jsonify({
    "items": [
      {
        "id": d.id,
        "reminder_id": d.reminder_id,
        "status": d.status,
        "channel": d.channel,
        "attempts": d.attempts,
        "last_error": d.last_error,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
      }
      for d in items
    ],
    "total": total,
    "page": page,
    "page_size": page_size,
  })
