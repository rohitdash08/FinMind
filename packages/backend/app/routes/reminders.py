from datetime import datetime, time, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Bill, Reminder, MAX_RETRIES
from ..observability import track_reminder_event
from ..services.reminders import send_reminder
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
                "retry_count": r.retry_count,
                "last_error": r.last_error,
                "exhausted": r.exhausted,
            }
            for r in items
        ]
    )


@bp.get("/stats")
@jwt_required()
def reminder_stats():
    """Monitoring endpoint: summary of reminder job status."""
    uid = int(get_jwt_identity())

    total = db.session.query(Reminder).filter_by(user_id=uid).count()
    sent = db.session.query(Reminder).filter_by(user_id=uid, sent=True).count()
    pending = (
        db.session.query(Reminder)
        .filter_by(user_id=uid, sent=False)
        .filter(Reminder.retry_count < MAX_RETRIES)
        .count()
    )
    exhausted = (
        db.session.query(Reminder)
        .filter_by(user_id=uid, sent=False)
        .filter(Reminder.retry_count >= MAX_RETRIES)
        .count()
    )
    retrying = (
        db.session.query(Reminder)
        .filter_by(user_id=uid, sent=False)
        .filter(Reminder.retry_count > 0)
        .count()
    )

    # Per-channel breakdown
    channels = {}
    for row in (
        db.session.query(Reminder.channel, Reminder.sent, db.func.count())
        .filter_by(user_id=uid)
        .group_by(Reminder.channel, Reminder.sent)
        .all()
    ):
        ch, is_sent, count = row
        if ch not in channels:
            channels[ch] = {"sent": 0, "failed_or_pending": 0}
        if is_sent:
            channels[ch]["sent"] += count
        else:
            channels[ch]["failed_or_pending"] += count

    # Next due reminder (oldest unsent)
    next_due = (
        db.session.query(Reminder)
        .filter_by(user_id=uid, sent=False)
        .filter(Reminder.retry_count < MAX_RETRIES)
        .order_by(Reminder.send_at)
        .first()
    )

    return jsonify(
        {
            "total": total,
            "sent": sent,
            "pending": pending,
            "exhausted": exhausted,
            "retrying": retrying,
            "channels": channels,
            "next_due_at": next_due.send_at.isoformat() if next_due else None,
            "max_retries": MAX_RETRIES,
        }
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
    """Process due reminders with resilient retry logic.

    Uses exponential backoff: retries at 1min, 5min, 25min intervals.
    Reminders are only marked sent=True on successful delivery.
    After MAX_RETRIES failures, the reminder is marked exhausted
    (retry_count >= MAX_RETRIES, sent=False).
    """
    uid = int(get_jwt_identity())
    now = datetime.utcnow()

    # Fetch all unsent reminders that haven't exhausted retries.
    # First attempts get a 1-min buffer; retries are checked at Python level.
    buffer_cutoff = now + timedelta(minutes=1)
    items = (
        db.session.query(Reminder)
        .filter(
            Reminder.user_id == uid,
            Reminder.sent.is_(False),
            Reminder.retry_count < MAX_RETRIES,
            Reminder.send_at <= buffer_cutoff,
        )
        .all()
    )

    processed = 0
    succeeded = 0
    failed = 0
    for r in items:
        # Check backoff at Python level for retries
        if r.retry_count > 0:
            backoff_seconds = 60 * (5 ** (r.retry_count - 1))
            next_attempt = r.send_at + timedelta(seconds=backoff_seconds)
            if now < next_attempt:
                continue  # Not time to retry yet

        error_msg = None
        try:
            ok = send_reminder(r)
        except Exception as exc:
            ok = False
            error_msg = str(exc)[:500]

        if ok:
            r.sent = True
            succeeded += 1
            track_reminder_event(event="sent", channel=r.channel, status="ok")
            logger.info("Reminder sent id=%s channel=%s", r.id, r.channel)
        else:
            r.retry_count += 1
            r.last_error = error_msg or "send failed"
            # Update send_at to now so backoff is calculated from last attempt
            r.send_at = datetime.utcnow()
            if r.retry_count >= MAX_RETRIES:
                track_reminder_event(event="exhausted", channel=r.channel, status="error")
                logger.warning(
                    "Reminder exhausted id=%s channel=%s after %s retries",
                    r.id, r.channel, r.retry_count,
                )
            else:
                track_reminder_event(event="retry", channel=r.channel, status="error")
                logger.info(
                    "Reminder retry id=%s channel=%s attempt=%s/%s",
                    r.id, r.channel, r.retry_count, MAX_RETRIES,
                )
            failed += 1
        processed += 1

    db.session.commit()
    logger.info(
        "Processed reminders user=%s total=%s succeeded=%s failed=%s",
        uid, processed, succeeded, failed,
    )
    return jsonify(
        processed=processed, succeeded=succeeded, failed=failed
    )


@bp.post("/<int:reminder_id>/retry")
@jwt_required()
def manual_retry(reminder_id: int):
    """Manually retry an exhausted reminder, resetting retry count."""
    uid = int(get_jwt_identity())
    r = db.session.get(Reminder, reminder_id)
    if not r or r.user_id != uid:
        return jsonify(error="not found"), 404
    if r.sent:
        return jsonify(error="already sent"), 400

    r.retry_count = 0
    r.last_error = None
    r.send_at = datetime.utcnow()
    db.session.commit()
    logger.info("Manual retry reset id=%s user=%s", r.id, uid)
    track_reminder_event(event="manual_retry", channel=r.channel)
    return jsonify(id=r.id, retry_count=0, message="Retry reset — will be picked up on next run")


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
