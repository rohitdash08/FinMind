"""Notification priority and grouping routes."""

from flask import Blueprint, jsonify, request
from app.services.notifications import get_notification_manager

bp = Blueprint("notifications", __name__)


@bp.route("/", methods=["GET"])
def list_notifications():
    """List notifications for a user."""
    user_id = request.args.get("user_id", 1, type=int)
    unread = request.args.get("unread", "false").lower() == "true"
    group = request.args.get("group")
    priority = request.args.get("priority")
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_notification_manager().get_notifications(
        user_id, unread_only=unread, group=group, priority=priority, limit=limit
    ))


@bp.route("/grouped", methods=["GET"])
def grouped_notifications():
    """Get notifications grouped by category."""
    user_id = request.args.get("user_id", 1, type=int)
    return jsonify(get_notification_manager().get_grouped(user_id))


@bp.route("/summary", methods=["GET"])
def notification_summary():
    """Get unread notification counts by priority."""
    user_id = request.args.get("user_id", 1, type=int)
    return jsonify(get_notification_manager().get_summary(user_id))


@bp.route("/", methods=["POST"])
def create_notification():
    """Create a notification."""
    data = request.get_json() or {}
    required = ["event_type", "title", "message", "user_id"]
    for f in required:
        if f not in data:
            return jsonify({"error": f"{f} is required"}), 400
    n = get_notification_manager().notify(
        event_type=data["event_type"], title=data["title"],
        message=data["message"], user_id=data["user_id"],
        data=data.get("data"),
    )
    return jsonify(n.to_dict()), 201


@bp.route("/<notification_id>/read", methods=["POST"])
def mark_read(notification_id):
    """Mark a notification as read."""
    user_id = request.args.get("user_id", 1, type=int)
    if get_notification_manager().mark_read(user_id, notification_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


@bp.route("/read-all", methods=["POST"])
def mark_all_read():
    """Mark all notifications as read."""
    user_id = request.args.get("user_id", 1, type=int)
    group = request.args.get("group")
    count = get_notification_manager().mark_all_read(user_id, group=group)
    return jsonify({"ok": True, "count": count})
