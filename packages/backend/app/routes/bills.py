from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Bill, BillCadence, User, WebhookEvent
from ..services.cache import cache_delete_patterns
from ..services.webhooks import WebhookService
import logging

bp = Blueprint("bills", __name__)
logger = logging.getLogger("finmind.bills")


@bp.get("")
@jwt_required()
def list_bills():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(Bill)
        .filter_by(user_id=uid, active=True)
        .order_by(Bill.next_due_date)
        .all()
    )
    logger.info("List bills user=%s count=%s", uid, len(items))
    return jsonify(
        [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value,
                "autopay_enabled": b.autopay_enabled,
                "channel_whatsapp": b.channel_whatsapp,
                "channel_email": b.channel_email,
            }
            for b in items
        ]
    )


@bp.post("")
@jwt_required()
def create_bill():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    b = Bill(
        user_id=uid,
        name=data["name"],
        amount=data["amount"],
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        next_due_date=date.fromisoformat(data["next_due_date"]),
        cadence=BillCadence(data.get("cadence", "MONTHLY")),
        autopay_enabled=bool(data.get("autopay_enabled", False)),
        channel_whatsapp=bool(data.get("channel_whatsapp", False)),
        channel_email=bool(data.get("channel_email", True)),
    )
    db.session.add(b)
    db.session.commit()
    logger.info("Created bill id=%s user=%s name=%s", b.id, uid, b.name)
    WebhookService.trigger_event(
        WebhookEvent.BILL_CREATED,
        _bill_to_dict(b),
        user_id=uid,
    )
    cache_delete_patterns(
        [f"user:{uid}:upcoming_bills*", f"user:{uid}:dashboard_summary:*"]
    )
    return jsonify(id=b.id), 201


@bp.post("/<int:bill_id>/pay")
@jwt_required()
def mark_paid(bill_id: int):
    uid = int(get_jwt_identity())
    b = db.session.get(Bill, bill_id)
    if not b or b.user_id != uid:
        return jsonify(error="not found"), 404
    # Move next due date based on cadence
    if b.cadence == BillCadence.MONTHLY:
        b.next_due_date = b.next_due_date + timedelta(days=30)
    elif b.cadence == BillCadence.WEEKLY:
        b.next_due_date = b.next_due_date + timedelta(days=7)
    elif b.cadence == BillCadence.YEARLY:
        b.next_due_date = b.next_due_date + timedelta(days=365)
    else:
        b.active = False
    db.session.commit()
    cache_delete_patterns(
        [f"user:{uid}:upcoming_bills*", f"user:{uid}:dashboard_summary:*"]
    )
    WebhookService.trigger_event(
        WebhookEvent.BILL_UPDATED,
        _bill_to_dict(b),
        user_id=uid,
    )
    logger.info(
        "Marked bill paid id=%s user=%s next_due_date=%s", b.id, uid, b.next_due_date
    )
    return jsonify(message="updated")


@bp.patch("/<int:bill_id>")
@jwt_required()
def update_bill(bill_id: int):
    uid = int(get_jwt_identity())
    b = db.session.get(Bill, bill_id)
    if not b or b.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        b.name = str(data.get("name") or "").strip() or b.name
    if "amount" in data:
        b.amount = data.get("amount")
    if "currency" in data:
        b.currency = str(data.get("currency") or "INR")[:10]
    if "next_due_date" in data:
        try:
            b.next_due_date = date.fromisoformat(str(data.get("next_due_date")))
        except ValueError:
            return jsonify(error="invalid next_due_date"), 400
    if "cadence" in data:
        try:
            b.cadence = BillCadence(str(data.get("cadence")))
        except ValueError:
            return jsonify(error="invalid cadence"), 400
    if "autopay_enabled" in data:
        b.autopay_enabled = bool(data.get("autopay_enabled"))
    if "channel_whatsapp" in data:
        b.channel_whatsapp = bool(data.get("channel_whatsapp"))
    if "channel_email" in data:
        b.channel_email = bool(data.get("channel_email"))
    if "active" in data:
        b.active = bool(data.get("active"))

    db.session.commit()
    cache_delete_patterns(
        [f"user:{uid}:upcoming_bills*", f"user:{uid}:dashboard_summary:*"]
    )
    WebhookService.trigger_event(
        WebhookEvent.BILL_UPDATED,
        _bill_to_dict(b),
        user_id=uid,
    )
    return jsonify(_bill_to_dict(b)), 200


@bp.delete("/<int:bill_id>")
@jwt_required()
def delete_bill(bill_id: int):
    uid = int(get_jwt_identity())
    b = db.session.get(Bill, bill_id)
    if not b or b.user_id != uid:
        return jsonify(error="not found"), 404

    payload = {"id": b.id}
    db.session.delete(b)
    db.session.commit()
    cache_delete_patterns(
        [f"user:{uid}:upcoming_bills*", f"user:{uid}:dashboard_summary:*"]
    )
    WebhookService.trigger_event(
        WebhookEvent.BILL_DELETED,
        payload,
        user_id=uid,
    )
    return jsonify(message="deleted"), 200


def _bill_to_dict(bill: Bill) -> dict:
    return {
        "id": bill.id,
        "name": bill.name,
        "amount": float(bill.amount),
        "currency": bill.currency,
        "next_due_date": bill.next_due_date.isoformat(),
        "cadence": bill.cadence.value,
        "autopay_enabled": bill.autopay_enabled,
        "channel_whatsapp": bill.channel_whatsapp,
        "channel_email": bill.channel_email,
        "active": bill.active,
    }
