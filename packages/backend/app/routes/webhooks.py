from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import WebhookSubscription, WebhookDeliveryLog
import logging

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks")

VALID_EVENT_TYPES = {
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "bill.created",
    "bill.paid",
    "user.registered",
}


@bp.get("")
@jwt_required()
def list_subscriptions():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(WebhookSubscription)
        .filter_by(user_id=uid)
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": s.id,
                "url": s.url,
                "event_type": s.event_type,
                "active": s.active,
                "created_at": s.created_at.isoformat(),
            }
            for s in items
        ]
    )


@bp.post("")
@jwt_required()
def create_subscription():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    event_type = (data.get("event_type") or "").strip()
    secret = (data.get("secret") or "").strip()

    if not url:
        return jsonify(error="url required"), 400
    if event_type not in VALID_EVENT_TYPES:
        return jsonify(
            error=f"invalid event_type, must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}"
        ), 400

    subscription = WebhookSubscription(
        user_id=uid,
        url=url,
        event_type=event_type,
    )
    db.session.add(subscription)
    db.session.commit()
    logger.info("Created webhook subscription id=%s user=%s event=%s", subscription.id, uid, event_type)
    return jsonify(
        id=subscription.id,
        url=subscription.url,
        event_type=subscription.event_type,
        active=subscription.active,
        created_at=subscription.created_at.isoformat(),
    ), 201


@bp.patch("/<int:subscription_id>")
@jwt_required()
def update_subscription(subscription_id: int):
    uid = int(get_jwt_identity())
    subscription = db.session.get(WebhookSubscription, subscription_id)
    if not subscription or subscription.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "url" in data:
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify(error="url required"), 400
        subscription.url = url
    if "event_type" in data:
        event_type = (data.get("event_type") or "").strip()
        if event_type not in VALID_EVENT_TYPES:
            return jsonify(
                error=f"invalid event_type, must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}"
            ), 400
        subscription.event_type = event_type
    if "active" in data:
        subscription.active = bool(data.get("active"))
    db.session.commit()
    return jsonify(
        id=subscription.id,
        url=subscription.url,
        event_type=subscription.event_type,
        active=subscription.active,
        created_at=subscription.created_at.isoformat(),
    )


@bp.delete("/<int:subscription_id>")
@jwt_required()
def delete_subscription(subscription_id: int):
    uid = int(get_jwt_identity())
    subscription = db.session.get(WebhookSubscription, subscription_id)
    if not subscription or subscription.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(subscription)
    db.session.commit()
    return jsonify(message="deleted")


@bp.get("/deliveries")
@jwt_required()
def list_deliveries():
    uid = int(get_jwt_identity())
    subscription_id = request.args.get("subscription_id")
    event_type = request.args.get("event_type")
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except ValueError:
        return jsonify(error="invalid limit"), 400

    sub_ids = (
        db.session.query(WebhookSubscription.id)
        .filter_by(user_id=uid)
        .all()
    )
    sub_id_list = [row[0] for row in sub_ids]
    if not sub_id_list:
        return jsonify([])
    q = db.session.query(WebhookDeliveryLog).filter(
        WebhookDeliveryLog.subscription_id.in_(sub_id_list)
    )
    if subscription_id:
        q = q.filter(WebhookDeliveryLog.subscription_id == int(subscription_id))
    if event_type:
        q = q.filter(WebhookDeliveryLog.event_type == event_type)

    items = q.order_by(WebhookDeliveryLog.delivered_at.desc()).limit(limit).all()
    return jsonify(
        [
            {
                "id": d.id,
                "subscription_id": d.subscription_id,
                "event_type": d.event_type,
                "attempt": d.attempt,
                "status_code": d.status_code,
                "success": d.success,
                "error_message": d.error_message,
                "delivered_at": d.delivered_at.isoformat(),
            }
            for d in items
        ]
    )
