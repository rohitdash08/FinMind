"""Webhook subscription management endpoints."""

import json
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import WebhookDeliveryLog, WebhookEvent, WebhookSubscription
from ..services.webhook import (
    SUPPORTED_EVENT_TYPES,
    deliver_test_ping,
    delivery_metrics,
    generate_secret,
)

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@bp.post("")
@jwt_required()
def create_subscription():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="url required"), 400

    event_types = data.get("event_types")
    if not isinstance(event_types, list) or not event_types:
        return jsonify(error="event_types must be a non-empty list"), 400

    invalid = [e for e in event_types if e not in SUPPORTED_EVENT_TYPES and e != "*"]
    if invalid:
        return jsonify(error=f"unsupported event types: {invalid}"), 400

    secret = generate_secret()
    sub = WebhookSubscription(
        user_id=uid,
        url=url,
        secret=secret,
        event_types=json.dumps(event_types),
        active=True,
    )
    db.session.add(sub)
    db.session.commit()

    logger.info("Created webhook subscription id=%s user=%s", sub.id, uid)
    return (
        jsonify(
            id=sub.id,
            url=sub.url,
            secret=secret,
            event_types=event_types,
            active=sub.active,
            created_at=sub.created_at.isoformat(),
        ),
        201,
    )


@bp.get("")
@jwt_required()
def list_subscriptions():
    uid = int(get_jwt_identity())
    subs = (
        db.session.query(WebhookSubscription)
        .filter_by(user_id=uid)
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )
    return jsonify([_sub_to_dict(s) for s in subs])


@bp.patch("/<int:sub_id>")
@jwt_required()
def update_subscription(sub_id: int):
    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "url" in data:
        url = (data["url"] or "").strip()
        if not url:
            return jsonify(error="url cannot be empty"), 400
        sub.url = url

    if "event_types" in data:
        event_types = data["event_types"]
        if not isinstance(event_types, list) or not event_types:
            return jsonify(error="event_types must be a non-empty list"), 400
        invalid = [
            e for e in event_types if e not in SUPPORTED_EVENT_TYPES and e != "*"
        ]
        if invalid:
            return jsonify(error=f"unsupported event types: {invalid}"), 400
        sub.event_types = json.dumps(event_types)

    if "active" in data:
        sub.active = bool(data["active"])
        if sub.active:
            sub.consecutive_failures = 0
            sub.disabled_at = None

    db.session.commit()
    logger.info("Updated webhook subscription id=%s user=%s", sub.id, uid)
    return jsonify(_sub_to_dict(sub))


@bp.delete("/<int:sub_id>")
@jwt_required()
def delete_subscription(sub_id: int):
    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(sub)
    db.session.commit()
    logger.info("Deleted webhook subscription id=%s user=%s", sub_id, uid)
    return jsonify(message="deleted")


# ---------------------------------------------------------------------------
# Delivery logs
# ---------------------------------------------------------------------------


@bp.get("/<int:sub_id>/deliveries")
@jwt_required()
def list_deliveries(sub_id: int):
    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404

    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(100, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    logs = (
        db.session.query(WebhookDeliveryLog)
        .filter_by(subscription_id=sub_id)
        .order_by(WebhookDeliveryLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    result = []
    for log in logs:
        event = db.session.get(WebhookEvent, log.event_id)
        result.append(
            {
                "id": log.id,
                "event_id": log.event_id,
                "event_type": event.event_type if event else None,
                "correlation_id": event.correlation_id if event else None,
                "status": log.status,
                "status_code": log.status_code,
                "attempt": log.attempt,
                "latency_ms": log.latency_ms,
                "failure_class": log.failure_class,
                "next_retry_at": (
                    log.next_retry_at.isoformat() if log.next_retry_at else None
                ),
                "delivered_at": (
                    log.delivered_at.isoformat() if log.delivered_at else None
                ),
                "created_at": log.created_at.isoformat(),
            }
        )

    return jsonify(result)


# ---------------------------------------------------------------------------
# Test ping
# ---------------------------------------------------------------------------


@bp.post("/<int:sub_id>/test")
@jwt_required()
def test_ping(sub_id: int):
    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404

    result = deliver_test_ping(sub)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Event types & metrics
# ---------------------------------------------------------------------------


@bp.get("/event-types")
@jwt_required()
def list_event_types():
    return jsonify(event_types=SUPPORTED_EVENT_TYPES)


@bp.get("/metrics")
@jwt_required()
def get_metrics():
    uid = int(get_jwt_identity())
    return jsonify(delivery_metrics(uid))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sub_to_dict(sub: WebhookSubscription) -> dict:
    try:
        event_types = json.loads(sub.event_types)
    except (json.JSONDecodeError, TypeError):
        event_types = []

    return {
        "id": sub.id,
        "url": sub.url,
        "event_types": event_types,
        "active": sub.active,
        "consecutive_failures": sub.consecutive_failures,
        "disabled_at": sub.disabled_at.isoformat() if sub.disabled_at else None,
        "created_at": sub.created_at.isoformat(),
    }
