from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Bill, BillCadence, User
from ..request_utils import get_json_object
from ..services.cache import cache_delete_patterns
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
    data = get_json_object()
    if data is None:
        return jsonify(error="json body must be an object"), 400
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return jsonify(error="invalid amount"), 400
    due_date = _parse_due_date(data.get("next_due_date"))
    if due_date is None:
        return jsonify(error="invalid next_due_date"), 400
    cadence = _parse_cadence(data.get("cadence", "MONTHLY"))
    if cadence is None:
        return jsonify(error="invalid cadence"), 400
    autopay_enabled = _parse_bool_flag(data.get("autopay_enabled"), default=False)
    if autopay_enabled is None:
        return jsonify(error="invalid autopay_enabled"), 400
    channel_whatsapp = _parse_bool_flag(data.get("channel_whatsapp"), default=False)
    if channel_whatsapp is None:
        return jsonify(error="invalid channel_whatsapp"), 400
    channel_email = _parse_bool_flag(data.get("channel_email"), default=True)
    if channel_email is None:
        return jsonify(error="invalid channel_email"), 400
    b = Bill(
        user_id=uid,
        name=name,
        amount=amount,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        next_due_date=due_date,
        cadence=BillCadence(cadence),
        autopay_enabled=autopay_enabled,
        channel_whatsapp=channel_whatsapp,
        channel_email=channel_email,
    )
    db.session.add(b)
    db.session.commit()
    logger.info("Created bill id=%s user=%s name=%s", b.id, uid, b.name)
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
    logger.info(
        "Marked bill paid id=%s user=%s next_due_date=%s", b.id, uid, b.next_due_date
    )
    return jsonify(message="updated")


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_due_date(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _parse_cadence(raw: str | None) -> str | None:
    cadence = str(raw or "").upper().strip()
    if cadence in {item.value for item in BillCadence}:
        return cadence
    return None


def _parse_bool_flag(raw, *, default: bool) -> bool | None:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in {0, 1}:
        return bool(raw)
    value = str(raw).strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    return None
