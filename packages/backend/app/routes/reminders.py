from datetime import datetime, time, timedelta
from sqlalchemy import func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Bill, Reminder
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
                "status": r.status,
                "attempt_count": r.attempt_count,
                "last_attempt_at": r.last_attempt_at.isoformat()
                if r.last_attempt_at
                else None,
                "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
                "failed_at": r.failed_at.isoformat() if r.failed_at else None,
                "last_error": r.last_error,
            }
            for r in items
        ]
    )


@bp.get("/reliability")
@jwt_required()
def reminder_reliability():
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(
            Reminder.channel,
            Reminder.status,
            func.count(Reminder.id),
            func.coalesce(func.sum(Reminder.attempt_count), 0),
        )
        .filter(Reminder.user_id == uid)
        .group_by(Reminder.channel, Reminder.status)
        .all()
    )
    by_channel: dict[str, dict[str, int]] = {}
    totals = {
        "total": 0,
        "pending": 0,
        "delivered": 0,
        "failed": 0,
        "attempts": 0,
    }
    for channel, status, count, attempts in rows:
        normalized = (status or "PENDING").lower()
        channel_metrics = by_channel.setdefault(
            channel,
            {"total": 0, "pending": 0, "delivered": 0, "failed": 0, "attempts": 0},
        )
        channel_metrics["total"] += count
        channel_metrics[normalized] = channel_metrics.get(normalized, 0) + count
        channel_metrics["attempts"] += int(attempts or 0)
        totals["total"] += count
        totals[normalized] = totals.get(normalized, 0) + count
        totals["attempts"] += int(attempts or 0)

    delivered = totals.get("delivered", 0)
    attempted_terminal = delivered + totals.get("failed", 0)
    delivery_rate = round(delivered / attempted_terminal, 4) if attempted_terminal else None
    return jsonify(totals=totals, by_channel=by_channel, delivery_rate=delivery_rate)


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
    items = (
        db.session.query(Reminder)
        .filter(
            Reminder.user_id == uid,
            Reminder.sent.is_(False),
            Reminder.send_at <= now,
        )
        .all()
    )
    processed = delivered = failed = 0
    for r in items:
        processed += 1
        r.attempt_count = (r.attempt_count or 0) + 1
        r.last_attempt_at = datetime.utcnow()
        try:
            was_delivered = bool(send_reminder(r))
        except Exception as exc:  # defensive: delivery adapters should not break batch
            logger.exception("Reminder delivery raised id=%s user=%s", r.id, uid)
            was_delivered = False
            r.last_error = str(exc)[:500]
        if was_delivered:
            r.sent = True
            r.status = "DELIVERED"
            r.delivered_at = datetime.utcnow()
            r.failed_at = None
            r.last_error = None
            delivered += 1
            track_reminder_event(event="sent", channel=r.channel, status="DELIVERED")
        else:
            r.status = "FAILED"
            r.failed_at = datetime.utcnow()
            if not r.last_error:
                r.last_error = "delivery adapter returned false"
            failed += 1
            track_reminder_event(event="sent", channel=r.channel, status="FAILED")
    db.session.commit()
    logger.info(
        "Processed due reminders user=%s processed=%s delivered=%s failed=%s",
        uid,
        processed,
        delivered,
        failed,
    )
    return jsonify(processed=processed, delivered=delivered, failed=failed)


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
