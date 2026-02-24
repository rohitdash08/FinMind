"""
notifications.py — Notification priority management endpoints.

GET  /notifications/grouped              — grouped view (by priority + type)
POST /notifications/<id>/priority        — update priority on a reminder
POST /notifications/bulk-prioritise      — auto-assign priorities for all pending
"""
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import NotificationPriority, Reminder
from ..services.notification_grouping import auto_priority, get_grouped_notifications

bp_notifications = Blueprint("notifications", __name__)
logger = logging.getLogger("finmind.notification_routes")

_VALID_PRIORITIES = {p.value for p in NotificationPriority}


@bp_notifications.get("/grouped")
@jwt_required()
def grouped_notifications():
    """Return pending notifications grouped by priority and type."""
    uid = int(get_jwt_identity())
    include_sent = request.args.get("include_sent", "false").lower() == "true"
    result = get_grouped_notifications(uid, db.session, include_sent=include_sent)
    return jsonify(result)


@bp_notifications.post("/<int:reminder_id>/priority")
@jwt_required()
def set_priority(reminder_id: int):
    """
    Manually set the priority of a notification.
    Body: {"priority": "URGENT"|"HIGH"|"NORMAL"|"LOW"}
    """
    uid = int(get_jwt_identity())
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder or reminder.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    priority = (data.get("priority") or "").upper()
    if priority not in _VALID_PRIORITIES:
        return jsonify(error=f"priority must be one of {sorted(_VALID_PRIORITIES)}"), 400

    reminder.priority = priority
    db.session.commit()
    logger.info("Set priority reminder=%s user=%s priority=%s", reminder_id, uid, priority)
    return jsonify({"reminder_id": reminder_id, "priority": priority})


@bp_notifications.post("/bulk-prioritise")
@jwt_required()
def bulk_prioritise():
    """
    Auto-assign priorities to all pending notifications based on context
    (bill due date proximity for BILL_REMINDERs, NORMAL for others).

    Returns count of updated notifications.
    """
    uid = int(get_jwt_identity())
    pending = (
        db.session.query(Reminder)
        .filter(Reminder.user_id == uid, Reminder.sent == False)  # noqa: E712
        .all()
    )
    updated = 0
    for r in pending:
        new_prio = auto_priority(r, db.session)
        if r.priority != new_prio:
            r.priority = new_prio
            updated += 1
    db.session.commit()
    logger.info("Bulk-prioritised user=%s updated=%d", uid, updated)
    return jsonify({"updated": updated, "total_pending": len(pending)})
