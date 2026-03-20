from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Notification
import logging

bp = Blueprint("notifications", __name__)
logger = logging.getLogger("finmind.notifications")


@bp.get("")
@jwt_required()
def list_notifications():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(Notification)
        .filter_by(user_id=uid)
        .order_by(Notification.created_at.desc())
        .all()
    )
    logger.info("List notifications user=%s count=%s", uid, len(items))

    # Group by type
    grouped: dict[str, list[dict]] = {}
    for n in items:
        entry = {
            "id": n.id,
            "type": n.type,
            "priority": n.priority,
            "group": n.group,
            "message": n.message,
            "read": n.read,
            "created_at": n.created_at.isoformat(),
        }
        grouped.setdefault(n.group, []).append(entry)

    unread_count = sum(1 for n in items if not n.read)

    return jsonify({"notifications": grouped, "unread_count": unread_count})


@bp.patch("/<int:notification_id>/read")
@jwt_required()
def mark_read(notification_id: int):
    uid = int(get_jwt_identity())
    n = db.session.get(Notification, notification_id)
    if not n or n.user_id != uid:
        return jsonify(error="not found"), 404
    n.read = True
    db.session.commit()
    logger.info("Marked notification read id=%s user=%s", n.id, uid)
    return jsonify(message="marked as read")


@bp.post("/mark-all-read")
@jwt_required()
def mark_all_read():
    uid = int(get_jwt_identity())
    count = (
        db.session.query(Notification)
        .filter_by(user_id=uid, read=False)
        .update({"read": True})
    )
    db.session.commit()
    logger.info("Marked all notifications read user=%s count=%s", uid, count)
    return jsonify(message="all marked as read", count=count)
