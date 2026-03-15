"""Routes for notification priority & grouping system."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.notification_priority import (
    create_notification,
    get_notifications,
    get_grouped_notifications,
    mark_read,
    mark_all_read,
    dismiss_notification,
    dismiss_group,
    get_unread_count,
    get_notification_stats,
)

bp = Blueprint("notification_priority", __name__)


@bp.post("/send")
@jwt_required()
def send_notification():
    """Create a new notification."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    title = data.get("title")
    message = data.get("message")
    if not title or not message:
        return jsonify({"error": "title and message are required"}), 400

    result = create_notification(
        user_id=user_id,
        title=title,
        message=message,
        priority=data.get("priority", "normal"),
        category=data.get("category", "general"),
        group_key=data.get("group_key"),
        action_url=data.get("action_url"),
        action_type=data.get("action_type"),
        metadata=data.get("extra_data"),
        expires_at=None,
    )
    return jsonify(result), 201


@bp.get("")
@jwt_required()
def list_notifications():
    """List notifications with priority sorting and filtering."""
    user_id = int(get_jwt_identity())

    result = get_notifications(
        user_id=user_id,
        category=request.args.get("category"),
        priority=request.args.get("priority"),
        is_read=_parse_bool(request.args.get("is_read")),
        group_key=request.args.get("group_key"),
        limit=int(request.args.get("limit", 50)),
        offset=int(request.args.get("offset", 0)),
    )
    return jsonify(result), 200


@bp.get("/grouped")
@jwt_required()
def grouped_notifications():
    """Get notifications grouped by group_key."""
    user_id = int(get_jwt_identity())
    category = request.args.get("category")
    result = get_grouped_notifications(user_id, category=category)
    return jsonify(result), 200


@bp.post("/<int:notification_id>/read")
@jwt_required()
def read_notification(notification_id):
    """Mark a notification as read."""
    user_id = int(get_jwt_identity())
    result = mark_read(notification_id, user_id)
    if not result:
        return jsonify({"error": "Notification not found"}), 404
    return jsonify(result), 200


@bp.post("/read-all")
@jwt_required()
def read_all():
    """Mark all notifications as read."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    result = mark_all_read(
        user_id,
        category=data.get("category"),
        group_key=data.get("group_key"),
    )
    return jsonify(result), 200


@bp.post("/<int:notification_id>/dismiss")
@jwt_required()
def dismiss(notification_id):
    """Dismiss a notification."""
    user_id = int(get_jwt_identity())
    result = dismiss_notification(notification_id, user_id)
    if not result:
        return jsonify({"error": "Notification not found"}), 404
    return jsonify(result), 200


@bp.post("/dismiss-group")
@jwt_required()
def dismiss_grp():
    """Dismiss all notifications in a group."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    group_key = data.get("group_key")
    if not group_key:
        return jsonify({"error": "group_key is required"}), 400
    result = dismiss_group(user_id, group_key)
    return jsonify(result), 200


@bp.get("/unread")
@jwt_required()
def unread():
    """Get unread notification counts."""
    user_id = int(get_jwt_identity())
    result = get_unread_count(user_id)
    return jsonify(result), 200


@bp.get("/stats")
@jwt_required()
def stats():
    """Get notification statistics."""
    user_id = int(get_jwt_identity())
    days = int(request.args.get("days", 30))
    result = get_notification_stats(user_id, days=days)
    return jsonify(result), 200


def _parse_bool(value):
    """Parse boolean query parameter."""
    if value is None:
        return None
    return value.lower() in ("true", "1", "yes")
