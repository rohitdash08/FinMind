from datetime import datetime, time, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Bill, Reminder, ReminderDelivery
from ..observability import track_reminder_event
from ..services.reminders import send_reminder, deliver_reminder, get_delivery_metrics, get_failed_reminders
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
                "delivered": r.delivered,
                "delivery_attempts": r.delivery_attempts,
                "last_attempt_at": r.last_attempt_at.isoformat() if r.last_attempt_at else None,
                "error_message": r.error_message,
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
    track_reminder_event(event="created", channel=r.channel)
    return jsonify(id=r.id), 201


@bp.patch("/<int:reminder_id>")
@jwt_required()
def update_reminder(reminder_id: int):
    uid = int(get_jwt_identity())
    r = db.session.query(Reminder).filter_by(id=reminder_id, user_id=uid).first()
    if not r:
        return jsonify({"error": "Reminder not found"}), 404
    
    data = request.get_json() or {}
    if "message" in data:
        r.message = data["message"]
    if "send_at" in data:
        r.send_at = datetime.fromisoformat(data["send_at"])
    if "channel" in data:
        r.channel = data["channel"]
    
    db.session.commit()
    logger.info("Updated reminder id=%s user=%s", r.id, uid)
    return jsonify({"message": "Reminder updated"})


@bp.delete("/<int:reminder_id>")
@jwt_required()
def delete_reminder(reminder_id: int):
    uid = int(get_jwt_identity())
    r = db.session.query(Reminder).filter_by(id=reminder_id, user_id=uid).first()
    if not r:
        return jsonify({"error": "Reminder not found"}), 404
    
    db.session.delete(r)
    db.session.commit()
    logger.info("Deleted reminder id=%s user=%s", reminder_id, uid)
    return jsonify({"message": "Reminder deleted"})


@bp.post("/bills/<int:bill_id>/schedule")
@jwt_required()
def schedule_bill_reminders(bill_id: int):
    uid = int(get_jwt_identity())
    bill = db.session.get(Bill, bill_id)
    if not bill or bill.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json(silent=True) or {}
    offsets = data.get("offsets_days")
    if offsets is None:
        offsets = [7, 3, 1]
    if not isinstance(offsets, list) or not offsets:
        return jsonify(error="offsets_days must be a non-empty list"), 400
    try:
        offsets = sorted({int(x) for x in offsets}, reverse=True)
    except (ValueError, TypeError):
        return jsonify(error="offsets_days must contain integers"), 400
    if any(x < 0 for x in offsets):
        return jsonify(error="offsets_days must be >= 0"), 400

    channels = _bill_channels(bill)
    created = 0
    for days_before in offsets:
        send_at = datetime.combine(
            bill.next_due_date - timedelta(days=days_before), time(9, 0, 0)
        )
        message = (
            f"Upcoming bill reminder: {bill.name} due on "
            f"{bill.next_due_date.isoformat()} in {days_before} day(s)."
        )
        for channel in channels:
            if _create_reminder_if_missing(
                uid=uid,
                bill_id=bill.id,
                channel=channel,
                send_at=send_at,
                message=message,
            ):
                created += 1
                track_reminder_event(event="scheduled", channel=channel)

    if bill.autopay_enabled:
        autopay_send_at = datetime.combine(
            bill.next_due_date - timedelta(days=1), time(9, 0, 0)
        )
        autopay_message = (
            f"Autopay check: {bill.name} is due on {bill.next_due_date.isoformat()}. "
            "Please ensure sufficient balance."
        )
        for channel in channels:
            if _create_reminder_if_missing(
                uid=uid,
                bill_id=bill.id,
                channel=channel,
                send_at=autopay_send_at,
                message=autopay_message,
            ):
                created += 1
                track_reminder_event(event="scheduled", channel=channel)

    db.session.commit()
    return jsonify(created=created), 200


@bp.post("/bills/<int:bill_id>/autopay-result")
@jwt_required()
def autopay_result_followup(bill_id: int):
    uid = int(get_jwt_identity())
    bill = db.session.get(Bill, bill_id)
    if not bill or bill.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json(silent=True) or {}
    status = str(data.get("status") or "").upper().strip()
    if status not in {"SUCCESS", "FAILED"}:
        return jsonify(error="status must be SUCCESS or FAILED"), 400

    channels = _bill_channels(bill)
    now = datetime.utcnow()
    if status == "SUCCESS":
        message = f"Autopay succeeded for {bill.name}."
    else:
        message = (
            f"Autopay failed for {bill.name}. Please review payment method and retry."
        )

    created = 0
    for channel in channels:
        db.session.add(
            Reminder(
                user_id=uid,
                bill_id=bill.id,
                message=message,
                send_at=now,
                channel=channel,
            )
        )
        created += 1
        track_reminder_event(event="autopay_followup", channel=channel, status=status)
    db.session.commit()
    return jsonify(created=created), 200


@bp.post("/run")
@jwt_required()
def run_due():
    """Process due reminders with delivery tracking and retry logic."""
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
    
    processed = 0
    delivered = 0
    failed = 0
    
    for r in items:
        success = deliver_reminder(r)
        processed += 1
        if success:
            delivered += 1
        else:
            failed += 1
    
    logger.info(
        "Processed due reminders user=%s total=%s delivered=%s failed=%s",
        uid, processed, delivered, failed
    )
    return jsonify({
        "processed": processed,
        "delivered": delivered,
        "failed": failed,
    })


@bp.get("/metrics")
@jwt_required()
def get_metrics():
    """Get delivery reliability metrics for the authenticated user."""
    uid = int(get_jwt_identity())
    days = request.args.get("days", 30, type=int)
    
    metrics = get_delivery_metrics(uid, days)
    logger.info("Retrieved delivery metrics user=%s days=%s", uid, days)
    return jsonify(metrics)


@bp.get("/failed")
@jwt_required()
def list_failed():
    """Get recent failed reminders that exhausted retry attempts."""
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 10, type=int)
    
    reminders = get_failed_reminders(uid, limit)
    logger.info("Listed failed reminders user=%s count=%s", uid, len(reminders))
    return jsonify([
        {
            "id": r.id,
            "message": r.message,
            "send_at": r.send_at.isoformat(),
            "channel": r.channel,
            "delivery_attempts": r.delivery_attempts,
            "last_attempt_at": r.last_attempt_at.isoformat() if r.last_attempt_at else None,
            "error_message": r.error_message,
        }
        for r in reminders
    ])


@bp.post("/<int:reminder_id>/retry")
@jwt_required()
def retry_reminder(reminder_id: int):
    """Manually retry a failed reminder."""
    uid = int(get_jwt_identity())
    r = db.session.query(Reminder).filter_by(id=reminder_id, user_id=uid).first()
    
    if not r:
        return jsonify({"error": "Reminder not found"}), 404
    
    if r.delivered:
        return jsonify({"error": "Reminder was already delivered"}), 400
    
    # Reset for retry
    r.delivery_attempts = 0
    r.sent = False
    r.send_at = datetime.utcnow()
    db.session.commit()
    
    # Attempt delivery
    success = deliver_reminder(r)
    
    logger.info("Manual retry reminder id=%s user=%s success=%s", reminder_id, uid, success)
    return jsonify({
        "success": success,
        "delivered": r.delivered,
        "attempts": r.delivery_attempts,
    })


@bp.get("/<int:reminder_id>/deliveries")
@jwt_required()
def get_reminder_deliveries(reminder_id: int):
    """Get delivery history for a specific reminder."""
    uid = int(get_jwt_identity())
    r = db.session.query(Reminder).filter_by(id=reminder_id, user_id=uid).first()
    
    if not r:
        return jsonify({"error": "Reminder not found"}), 404
    
    deliveries = (
        db.session.query(ReminderDelivery)
        .filter_by(reminder_id=reminder_id)
        .order_by(ReminderDelivery.attempted_at.desc())
        .all()
    )
    
    return jsonify([
        {
            "id": d.id,
            "attempted_at": d.attempted_at.isoformat(),
            "success": d.success,
            "channel": d.channel,
            "error_message": d.error_message,
            "response_time_ms": d.response_time_ms,
        }
        for d in deliveries
    ])


def _bill_channels(bill: Bill) -> list[str]:
    channels: list[str] = []
    if bill.channel_email:
        channels.append("email")
    if bill.channel_whatsapp:
        channels.append("whatsapp")
    if not channels:
        channels.append("email")
    return channels


def _create_reminder_if_missing(
    *,
    uid: int,
    bill_id: int,
    channel: str,
    send_at: datetime,
    message: str,
) -> bool:
    exists = (
        db.session.query(Reminder.id)
        .filter_by(
            user_id=uid,
            bill_id=bill_id,
            channel=channel,
            send_at=send_at,
            message=message,
        )
        .first()
    )
    if exists:
        return False
    db.session.add(
        Reminder(
            user_id=uid,
            bill_id=bill_id,
            channel=channel,
            send_at=send_at,
            message=message,
        )
    )
    return True
