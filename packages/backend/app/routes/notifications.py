from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.notifications import notification_service
import logging

bp = Blueprint("notifications", __name__)
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_GROUPS = {"bills", "expenses", "budget", "security", "system"}


@bp.post("")
@jwt_required()
def create_notification():
  uid = int(get_jwt_identity())
  data = request.get_json() or {}

  title = data.get("title")
  message = data.get("message")
  if not title or not message:
    return jsonify(error="title and message are required"), 400

  priority = data.get("priority", "medium")
  if priority not in VALID_PRIORITIES:
    return jsonify(error=f"priority must be one of {sorted(VALID_PRIORITIES)}"), 400

  group = data.get("group", "system")
  if group not in VALID_GROUPS:
    return jsonify(error=f"group must be one of {sorted(VALID_GROUPS)}"), 400

  n = notification_service.create(
    user_id=uid,
    title=title,
    message=message,
    priority=priority,
    group=group,
    action_url=data.get("action_url"),
    metadata=data.get("metadata"),
  )
  logger.info("Created notification id=%s user=%s", n.id, uid)
  return jsonify(
    {
      "id": n.id,
      "title": n.title,
      "message": n.message,
      "priority": n.priority,
      "group": n.group,
      "read": n.read,
      "action_url": n.action_url,
      "metadata": n.metadata_json,
      "created_at": n.created_at.isoformat(),
      "read_at": n.read_at.isoformat() if n.read_at else None,
    }
  ), 201


logger = logging.getLogger("finmind.notifications")


@bp.get("")
@jwt_required()
def list_notifications():
  uid = int(get_jwt_identity())
  unread_only = request.args.get("unread_only", "false").lower() == "true"
  group = request.args.get("group")
  page = max(int(request.args.get("page", 1)), 1)
  page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)

  items, total = notification_service.get_user_notifications(
    user_id=uid,
    unread_only=unread_only,
    group=group,
    page=page,
    page_size=page_size,
  )
  logger.info("List notifications user=%s count=%s", uid, total)
  return jsonify(
    {
      "items": [
        {
          "id": n.id,
          "title": n.title,
          "message": n.message,
          "priority": n.priority,
          "group": n.group,
          "read": n.read,
          "action_url": n.action_url,
          "metadata": n.metadata_json,
          "created_at": n.created_at.isoformat(),
          "read_at": n.read_at.isoformat() if n.read_at else None,
        }
        for n in items
      ],
      "total": total,
      "page": page,
      "page_size": page_size,
    }
  )


@bp.get("/unread-count")
@jwt_required()
def unread_count():
  uid = int(get_jwt_identity())
  counts = notification_service.get_unread_count(uid)
  total = sum(counts.values())
  logger.info("Unread count user=%s total=%s", uid, total)
  return jsonify({"total": total, "by_group": counts})


@bp.patch("/<int:notification_id>/read")
@jwt_required()
def mark_read(notification_id):
  uid = int(get_jwt_identity())
  n = notification_service.mark_read(notification_id, uid)
  if not n:
    return jsonify(error="not found"), 404
  logger.info("Marked read notification=%s user=%s", notification_id, uid)
  return jsonify(
    {
      "id": n.id,
      "read": n.read,
      "read_at": n.read_at.isoformat() if n.read_at else None,
    }
  )


@bp.patch("/read-all")
@jwt_required()
def mark_all_read():
  uid = int(get_jwt_identity())
  group = request.args.get("group")
  notification_service.mark_all_read(uid, group=group)
  logger.info("Marked all read user=%s group=%s", uid, group)
  return jsonify(ok=True)


@bp.delete("/<int:notification_id>")
@jwt_required()
def delete_notification(notification_id):
  uid = int(get_jwt_identity())
  deleted = notification_service.delete(notification_id, uid)
  if not deleted:
    return jsonify(error="not found"), 404
  logger.info("Deleted notification=%s user=%s", notification_id, uid)
  return jsonify(ok=True)
