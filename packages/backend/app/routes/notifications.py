import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import NotificationPriority
from ..services.notification_priority import (
    get_unread_count,
    list_notifications,
    mark_all_read,
    mark_read,
)

bp = Blueprint("notifications", __name__)
logger = logging.getLogger("finmind.notifications")


@bp.get("")
@jwt_required()
def list_user_notifications():
    uid = int(get_jwt_identity())
    unread_only = request.args.get("unread_only", "").lower() in ("true", "1")
    priority_str = request.args.get("priority", "").upper().strip()
    priority = None
    if priority_str in ("URGENT", "HIGH", "NORMAL", "LOW"):
        priority = NotificationPriority[priority_str]
    limit = request.args.get("limit", 50, type=int)
    items = list_notifications(uid, unread_only=unread_only, priority=priority, limit=min(limit, 200))
    return jsonify(items)


@bp.get("/unread-count")
@jwt_required()
def unread_count():
    uid = int(get_jwt_identity())
    return jsonify(get_unread_count(uid))


@bp.post("/<int:notification_id>/read")
@jwt_required()
def mark_notification_read(notification_id: int):
    uid = int(get_jwt_identity())
    if not mark_read(notification_id, uid):
        return jsonify(error="not found"), 404
    return jsonify(message="marked read"), 200


@bp.post("/mark-all-read")
@jwt_required()
def mark_all_notifications_read():
    uid = int(get_jwt_identity())
    count = mark_all_read(uid)
    return jsonify(marked=count)
