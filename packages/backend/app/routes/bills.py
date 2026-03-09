from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import and_, or_
from ..extensions import db
from ..models import Bill, BillCadence, User
from ..services.cache import cache_delete_patterns
from ..services.households import (
    can_access_scope,
    get_household_ids,
    get_household_member_user_ids,
    is_household_member,
)
import logging

bp = Blueprint("bills", __name__)
logger = logging.getLogger("finmind.bills")


@bp.get("")
@jwt_required()
def list_bills():
    uid = int(get_jwt_identity())
    household_ids = list(get_household_ids(uid))
    q = db.session.query(Bill).filter(Bill.active.is_(True))
    if household_ids:
        q = q.filter(
            or_(
                and_(Bill.user_id == uid, Bill.household_id.is_(None)),
                Bill.household_id.in_(household_ids),
            )
        )
    else:
        q = q.filter(and_(Bill.user_id == uid, Bill.household_id.is_(None)))
    items = q.order_by(Bill.next_due_date).all()
    logger.info("List bills user=%s count=%s", uid, len(items))
    return jsonify(
        [
            {
                "id": b.id,
                "household_id": b.household_id,
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
    household_id = data.get("household_id")
    if household_id is not None:
        try:
            household_id = int(household_id)
        except (TypeError, ValueError):
            return jsonify(error="invalid household_id"), 400
        if not is_household_member(uid, household_id):
            return jsonify(error="forbidden household"), 403
    b = Bill(
        user_id=uid,
        household_id=household_id,
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
    _invalidate_bill_cache(uid, b.household_id)
    return jsonify(id=b.id), 201


@bp.post("/<int:bill_id>/pay")
@jwt_required()
def mark_paid(bill_id: int):
    uid = int(get_jwt_identity())
    b = db.session.get(Bill, bill_id)
    if not b or not can_access_scope(uid, b.user_id, b.household_id):
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
    _invalidate_bill_cache(uid, b.household_id)
    logger.info(
        "Marked bill paid id=%s user=%s next_due_date=%s", b.id, uid, b.next_due_date
    )
    return jsonify(message="updated")


def _invalidate_bill_cache(uid: int, household_id: int | None):
    affected_users = {uid, *get_household_member_user_ids(household_id)}
    for affected_uid in affected_users:
        cache_delete_patterns(
            [
                f"user:{affected_uid}:upcoming_bills*",
                f"user:{affected_uid}:dashboard_summary:*",
            ]
        )
