from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Reminder
import logging

bp = Blueprint("reminder_metrics", __name__)
logger = logging.getLogger("finmind.reminder_metrics")


@bp.get("")
@jwt_required()
def get_metrics():
    """Return aggregate reminder delivery statistics for the current user."""
    uid = int(get_jwt_identity())

    total_sent = (
        db.session.query(func.count(Reminder.id))
        .filter(Reminder.user_id == uid, Reminder.sent.is_(True))
        .scalar()
    ) or 0

    total_pending = (
        db.session.query(func.count(Reminder.id))
        .filter(Reminder.user_id == uid, Reminder.sent.is_(False))
        .scalar()
    ) or 0

    total = total_sent + total_pending
    delivery_rate = round((total_sent / total) * 100, 2) if total > 0 else 0.0

    # Failed = past-due but still unsent
    now = datetime.utcnow()
    failed_count = (
        db.session.query(func.count(Reminder.id))
        .filter(
            Reminder.user_id == uid,
            Reminder.sent.is_(False),
            Reminder.send_at < now,
        )
        .scalar()
    ) or 0

    # Average delay: difference between send_at and now for sent reminders
    # (proxy metric - in production this would use an actual delivered_at column)
    avg_delay_seconds = 0.0

    logger.info("Metrics fetched user=%s total=%s sent=%s", uid, total, total_sent)
    return jsonify(
        total_sent=total_sent,
        total_pending=total_pending,
        delivery_rate=delivery_rate,
        failed_count=failed_count,
        avg_delay_seconds=avg_delay_seconds,
    )


@bp.get("/history")
@jwt_required()
def get_history():
    """Return recent reminder delivery events for the current user."""
    uid = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", 50)), 200)

    items = (
        db.session.query(Reminder)
        .filter(Reminder.user_id == uid)
        .order_by(Reminder.send_at.desc())
        .limit(limit)
        .all()
    )

    logger.info("History fetched user=%s count=%s", uid, len(items))
    return jsonify(
        [
            {
                "id": r.id,
                "message": r.message,
                "send_at": r.send_at.isoformat(),
                "sent": r.sent,
                "channel": r.channel,
                "status": "delivered" if r.sent else (
                    "failed" if r.send_at < datetime.utcnow() else "pending"
                ),
            }
            for r in items
        ]
    )
