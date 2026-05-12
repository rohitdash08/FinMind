from datetime import datetime, time, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Bill, Reminder
from ..observability import track_reminder_event
from ..services.reminders import send_reminder
from ..services.reminder_jobs import process_due_reminders, reset_failed_reminder
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
                "retry_status": r.retry_status,
                "retry_count": r.retry_count,
                "max_retries": r.max_retries,
                "next_retry_at": (
                    r.next_retry_at.isoformat() if r.next_retry_at else None
                ),
                "last_attempt_at": (
                    r.last_attempt_at.isoformat() if r.last_attempt_at else None
                ),
                "last_error": r.last_error,
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
    uid = int(get_jwt_identity())
    now = datetime.utcnow() + timedelta(minutes=1)
    result = process_due_reminders(user_id=uid, now=now, sender=send_reminder)
    for channel in result.sent_channels or []:
        track_reminder_event(event="sent", channel=channel)
    logger.info(
        "Processed due reminders user=%s processed=%s sent=%s retrying=%s failed=%s",
        uid,
        result.processed,
        result.sent,
        result.retrying,
        result.failed,
    )
    return jsonify(result.to_dict())


@bp.get("/jobs/status")
@jwt_required()
def jobs_status():
    uid = int(get_jwt_identity())
    rows = db.session.query(Reminder).filter_by(user_id=uid).all()
    total = len(rows)
    sent = sum(1 for r in rows if r.sent)
    failed = sum(1 for r in rows if r.retry_status == "FAILED")
    retrying = sum(1 for r in rows if r.retry_status == "RETRYING")
    pending = sum(1 for r in rows if not r.sent and r.retry_status == "PENDING")
    return jsonify(
        total=total,
        sent=sent,
        pending=pending,
        retrying=retrying,
        failed=failed,
        healthy=failed == 0,
    )


@bp.get("/jobs/failed")
@jwt_required()
def failed_jobs():
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(Reminder)
        .filter_by(user_id=uid, retry_status="FAILED")
        .order_by(Reminder.failed_at.desc().nullslast(), Reminder.id.desc())
        .all()
    )
    return jsonify([_job_to_dict(r) for r in rows])


@bp.post("/jobs/<int:reminder_id>/retry")
@jwt_required()
def retry_failed_job(reminder_id: int):
    uid = int(get_jwt_identity())
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder or reminder.user_id != uid:
        return jsonify(error="not found"), 404
    if reminder.sent:
        return jsonify(error="reminder already sent"), 400
    reset_failed_reminder(reminder)
    db.session.commit()
    return jsonify(_job_to_dict(reminder)), 200


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


def _job_to_dict(reminder: Reminder) -> dict:
    return {
        "id": reminder.id,
        "message": reminder.message,
        "channel": reminder.channel,
        "send_at": reminder.send_at.isoformat(),
        "sent": reminder.sent,
        "retry_status": reminder.retry_status,
        "retry_count": reminder.retry_count,
        "max_retries": reminder.max_retries,
        "next_retry_at": (
            reminder.next_retry_at.isoformat() if reminder.next_retry_at else None
        ),
        "last_attempt_at": (
            reminder.last_attempt_at.isoformat() if reminder.last_attempt_at else None
        ),
        "failed_at": reminder.failed_at.isoformat() if reminder.failed_at else None,
        "last_error": reminder.last_error,
    }
