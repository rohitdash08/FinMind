from datetime import datetime, time, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Bill, Reminder
from ..observability import track_reminder_event
from ..services.reminder_jobs import (
    VALID_STATUSES,
    configured_max_attempts,
    process_due_reminders,
    reminder_job_stats,
    reminder_jobs_query,
    reset_reminder_for_retry,
    serialize_reminder_job,
)
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
    return jsonify([serialize_reminder_job(r) for r in items])


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
        max_attempts=configured_max_attempts(),
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
                max_attempts=configured_max_attempts(),
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
    summary = process_due_reminders(uid)
    logger.info("Processed due reminders user=%s result=%s", uid, summary)
    return jsonify(summary)


@bp.get("/jobs/stats")
@jwt_required()
def job_stats():
    uid = int(get_jwt_identity())
    return jsonify(reminder_job_stats(uid))


@bp.get("/jobs")
@jwt_required()
def list_jobs():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    if status:
        status = status.upper().strip()
        if status not in VALID_STATUSES:
            return jsonify(error="unsupported status"), 400
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    except ValueError:
        return jsonify(error="limit must be an integer"), 400

    jobs = reminder_jobs_query(uid, status=status).limit(limit).all()
    return jsonify([serialize_reminder_job(job) for job in jobs])


@bp.post("/<int:reminder_id>/retry")
@jwt_required()
def retry_reminder(reminder_id: int):
    uid = int(get_jwt_identity())
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder or reminder.user_id != uid:
        return jsonify(error="not found"), 404
    reset_reminder_for_retry(reminder)
    db.session.commit()
    logger.info("Reset reminder job for retry id=%s user=%s", reminder.id, uid)
    return jsonify(serialize_reminder_job(reminder)), 200


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
            max_attempts=configured_max_attempts(),
        )
    )
    return True
