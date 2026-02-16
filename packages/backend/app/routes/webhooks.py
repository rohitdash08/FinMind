"""Webhook management routes.

Endpoints:
  POST   /webhooks              Register a new webhook
  GET    /webhooks              List user's webhooks
  GET    /webhooks/<id>         Get webhook details
  PATCH  /webhooks/<id>         Update webhook
  DELETE /webhooks/<id>         Delete webhook
  GET    /webhooks/<id>/deliveries  List delivery attempts
  POST   /webhooks/<id>/test    Send a test event
"""

import json
import logging
import secrets
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import (
    DeliveryStatus,
    Webhook,
    WebhookDelivery,
    WebhookEventType,
)
from ..services.webhooks import emit_event

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks")

VALID_EVENTS = {e.value for e in WebhookEventType} | {"*"}


@bp.post("")
@jwt_required()
def create_webhook():
    """Register a new webhook endpoint."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    url = (data.get("url") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return jsonify(error="valid url required"), 400

    events = data.get("events") or ["*"]
    if not isinstance(events, list):
        return jsonify(error="events must be an array"), 400
    invalid = [e for e in events if e not in VALID_EVENTS]
    if invalid:
        return jsonify(error=f"invalid event types: {invalid}"), 400

    # Generate a cryptographic secret for signing
    secret = data.get("secret") or secrets.token_hex(32)

    wh = Webhook(
        user_id=uid,
        url=url,
        secret=secret,
        events=json.dumps(events),
        active=True,
    )
    db.session.add(wh)
    db.session.commit()

    logger.info("Webhook created id=%s user=%s url=%s", wh.id, uid, url)
    return jsonify(_webhook_to_dict(wh, include_secret=True)), 201


@bp.get("")
@jwt_required()
def list_webhooks():
    """List all webhooks for the authenticated user."""
    uid = int(get_jwt_identity())
    webhooks = (
        db.session.query(Webhook)
        .filter_by(user_id=uid)
        .order_by(Webhook.created_at.desc())
        .all()
    )
    return jsonify([_webhook_to_dict(wh) for wh in webhooks])


@bp.get("/<int:webhook_id>")
@jwt_required()
def get_webhook(webhook_id: int):
    """Get a single webhook's details."""
    uid = int(get_jwt_identity())
    wh = db.session.get(Webhook, webhook_id)
    if not wh or wh.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_webhook_to_dict(wh))


@bp.patch("/<int:webhook_id>")
@jwt_required()
def update_webhook(webhook_id: int):
    """Update webhook URL, events, or active status."""
    uid = int(get_jwt_identity())
    wh = db.session.get(Webhook, webhook_id)
    if not wh or wh.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "url" in data:
        url = (data["url"] or "").strip()
        if not url.startswith(("http://", "https://")):
            return jsonify(error="valid url required"), 400
        wh.url = url

    if "events" in data:
        events = data["events"]
        if not isinstance(events, list):
            return jsonify(error="events must be an array"), 400
        invalid = [e for e in events if e not in VALID_EVENTS]
        if invalid:
            return jsonify(error=f"invalid event types: {invalid}"), 400
        wh.events = json.dumps(events)

    if "active" in data:
        wh.active = bool(data["active"])
        if wh.active:
            wh.failure_count = 0  # Reset on re-enable

    wh.updated_at = datetime.utcnow()
    db.session.commit()

    logger.info("Webhook updated id=%s", wh.id)
    return jsonify(_webhook_to_dict(wh))


@bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook(webhook_id: int):
    """Delete a webhook and all its deliveries."""
    uid = int(get_jwt_identity())
    wh = db.session.get(Webhook, webhook_id)
    if not wh or wh.user_id != uid:
        return jsonify(error="not found"), 404

    # Delete deliveries first
    db.session.query(WebhookDelivery).filter_by(webhook_id=wh.id).delete()
    db.session.delete(wh)
    db.session.commit()

    logger.info("Webhook deleted id=%s", wh.id)
    return jsonify(message="deleted")


@bp.get("/<int:webhook_id>/deliveries")
@jwt_required()
def list_deliveries(webhook_id: int):
    """List delivery attempts for a webhook (newest first)."""
    uid = int(get_jwt_identity())
    wh = db.session.get(Webhook, webhook_id)
    if not wh or wh.user_id != uid:
        return jsonify(error="not found"), 404

    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(100, max(1, int(request.args.get("page_size", "20"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    status_filter = request.args.get("status")

    q = db.session.query(WebhookDelivery).filter_by(webhook_id=wh.id)
    if status_filter:
        q = q.filter_by(status=status_filter)

    deliveries = (
        q.order_by(WebhookDelivery.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify([_delivery_to_dict(d) for d in deliveries])


@bp.post("/<int:webhook_id>/test")
@jwt_required()
def test_webhook(webhook_id: int):
    """Send a test ping event to the webhook."""
    uid = int(get_jwt_identity())
    wh = db.session.get(Webhook, webhook_id)
    if not wh or wh.user_id != uid:
        return jsonify(error="not found"), 404
    if not wh.active:
        return jsonify(error="webhook is disabled"), 400

    delivery_ids = emit_event(
        user_id=uid,
        event_type="ping",
        data={"message": "Test event from FinMind"},
    )
    return jsonify(message="test event sent", delivery_ids=delivery_ids)


def _webhook_to_dict(wh: Webhook, include_secret: bool = False) -> dict:
    result = {
        "id": wh.id,
        "url": wh.url,
        "events": json.loads(wh.events) if wh.events else [],
        "active": wh.active,
        "failure_count": wh.failure_count,
        "created_at": wh.created_at.isoformat() if wh.created_at else None,
        "updated_at": wh.updated_at.isoformat() if wh.updated_at else None,
    }
    if include_secret:
        result["secret"] = wh.secret
    return result


def _delivery_to_dict(d: WebhookDelivery) -> dict:
    return {
        "id": d.id,
        "delivery_id": d.delivery_id,
        "event_type": d.event_type,
        "status": d.status,
        "attempts": d.attempts,
        "max_retries": d.max_retries,
        "last_status_code": d.last_status_code,
        "last_response_ms": d.last_response_ms,
        "last_error": d.last_error,
        "next_retry_at": d.next_retry_at.isoformat() if d.next_retry_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
    }
