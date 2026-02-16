from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Reminder
from ..services.reminders import send_reminder
from ..services.webhook import emit_event
import logging

bp = Blueprint("reminders", __name__)
logger = logging.getLogger("finmind.reminders")


@bp.get("")
@jwt_required()
def list_reminders():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(Reminder)
        .filter_by(user_id=uid)
        .order_by(Reminder.send_at)
        .all()
    )
    logger.info("List reminders user=%s count=%s", uid, len(items))
    return jsonify(
        [
            {
                "id": r.id,
                "message": r.message,
                "send_at": r.send_at.isoformat(),
                "sent": r.sent,
                "channel": r.channel,
            }
            for r in items
        ]
    )


@bp.post("")
@jwt_required()
def create_reminder():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    r = Reminder(
        user_id=uid,
        message=data["message"],
        send_at=datetime.fromisoformat(data["send_at"]),
        channel=data.get("channel", "email"),
    )
    db.session.add(r)
    db.session.commit()
    logger.info("Created reminder id=%s user=%s", r.id, uid)
    return jsonify(id=r.id), 201


@bp.post("/run")
@jwt_required()
def run_due():
    uid = int(get_jwt_identity())
    now = datetime.utcnow() + timedelta(minutes=1)
    items = (
        db.session.query(Reminder)
        .filter(
            Reminder.user_id == uid,
            Reminder.sent.is_(False),
            Reminder.send_at <= now,
        )
        .all()
    )
    for r in items:
        send_reminder(r)
        r.sent = True
        try:
            emit_event(
                uid,
                "reminder.triggered",
                {
                    "id": r.id,
                    "message": r.message,
                    "channel": r.channel,
                    "send_at": r.send_at.isoformat(),
                },
            )
        except Exception:
            logger.debug("Webhook emit failed for reminder.triggered", exc_info=True)
    db.session.commit()
    logger.info("Processed due reminders user=%s count=%s", uid, len(items))
    return jsonify(processed=len(items))
