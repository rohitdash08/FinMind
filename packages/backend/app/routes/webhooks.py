"""
Webhook Event System routes (Issue #77).

Endpoints:
  GET    /webhooks                    → list user's webhooks
  POST   /webhooks                    → register a webhook
  GET    /webhooks/<id>               → get webhook detail
  PATCH  /webhooks/<id>               → update webhook (url, events, active)
  DELETE /webhooks/<id>               → delete webhook
  GET    /webhooks/<id>/deliveries    → list recent deliveries
  POST   /webhooks/<id>/test          → send a test ping event
  GET    /webhooks/event-types        → list supported event types
  POST   /webhooks/retry              → trigger retry of failed deliveries (admin/ops)
"""

from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models_webhooks import Webhook, WebhookDelivery
from ..services.webhooks import (
    VALID_EVENT_TYPES,
    deliver_webhook,
    dispatch_event,
    generate_secret,
    retry_failed_deliveries,
)

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks_routes")


def _get_or_404(webhook_id: int, uid: int):
    wh = db.session.get(Webhook, webhook_id)
    if not wh or wh.user_id != uid:
        return None
    return wh


def _wh_to_dict(wh: Webhook, include_secret: bool = False) -> dict:
    d = {
        "id":          wh.id,
        "url":         wh.url,
        "events":      json.loads(wh.events) if isinstance(wh.events, str) else wh.events,
        "active":      wh.active,
        "description": wh.description,
        "created_at":  wh.created_at.isoformat(),
        "updated_at":  wh.updated_at.isoformat(),
    }
    if include_secret:
        d["secret"] = wh.secret
    return d


def _delivery_to_dict(d: WebhookDelivery) -> dict:
    return {
        "id":            d.id,
        "webhook_id":    d.webhook_id,
        "event_type":    d.event_type,
        "attempt":       d.attempt,
        "status":        d.status,
        "response_code": d.response_code,
        "error_message": d.error_message,
        "delivered_at":  d.delivered_at.isoformat() if d.delivered_at else None,
        "next_retry_at": d.next_retry_at.isoformat() if d.next_retry_at else None,
        "created_at":    d.created_at.isoformat(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@bp.get("/event-types")
@jwt_required()
def event_types():
    """Return all supported webhook event types with descriptions."""
    docs = {
        "expense.created":  "Fired when a new expense is recorded",
        "expense.updated":  "Fired when an expense is modified",
        "expense.deleted":  "Fired when an expense is deleted",
        "bill.created":     "Fired when a new bill is added",
        "bill.updated":     "Fired when a bill is modified",
        "bill.due":         "Fired when a bill's due date is reached",
        "reminder.sent":    "Fired when a reminder is dispatched successfully",
        "reminder.failed":  "Fired when a reminder dispatch fails",
        "goal.created":     "Fired when a savings goal is created",
        "goal.achieved":    "Fired when a savings goal is reached",
        "budget.exceeded":  "Fired when spending exceeds a budget limit",
        "user.registered":  "Fired when a new user completes registration",
    }
    return jsonify([{"event": e, "description": docs.get(e, "")} for e in sorted(VALID_EVENT_TYPES)])


@bp.get("")
@jwt_required()
def list_webhooks():
    uid = int(get_jwt_identity())
    webhooks = db.session.query(Webhook).filter_by(user_id=uid).order_by(Webhook.created_at.desc()).all()
    return jsonify([_wh_to_dict(wh) for wh in webhooks])


@bp.post("")
@jwt_required()
def create_webhook():
    uid  = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    url = str(data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return jsonify(error="url must be a valid HTTP/HTTPS URL"), 400

    events = data.get("events") or []
    if not isinstance(events, list):
        return jsonify(error="events must be a list of event type strings"), 400

    invalid = [e for e in events if e not in VALID_EVENT_TYPES]
    if invalid:
        return jsonify(error=f"unknown event types: {invalid}", valid=sorted(VALID_EVENT_TYPES)), 400

    secret = data.get("secret") or generate_secret()

    wh = Webhook(
        user_id=uid,
        url=url,
        secret=secret,
        events=json.dumps(events),
        active=True,
        description=(data.get("description") or "")[:255] or None,
    )
    db.session.add(wh)
    db.session.commit()
    logger.info("Webhook created id=%d uid=%d url=%s events=%s", wh.id, uid, url, events)
    # Return secret only on creation
    return jsonify(_wh_to_dict(wh, include_secret=True)), 201


@bp.get("/<int:webhook_id>")
@jwt_required()
def get_webhook(webhook_id: int):
    uid = int(get_jwt_identity())
    wh = _get_or_404(webhook_id, uid)
    if not wh:
        return jsonify(error="not found"), 404
    return jsonify(_wh_to_dict(wh))


@bp.patch("/<int:webhook_id>")
@jwt_required()
def update_webhook(webhook_id: int):
    uid = int(get_jwt_identity())
    wh  = _get_or_404(webhook_id, uid)
    if not wh:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}

    if "url" in data:
        url = str(data["url"]).strip()
        if not url.startswith(("http://", "https://")):
            return jsonify(error="url must be a valid HTTP/HTTPS URL"), 400
        wh.url = url

    if "events" in data:
        if not isinstance(data["events"], list):
            return jsonify(error="events must be a list"), 400
        invalid = [e for e in data["events"] if e not in VALID_EVENT_TYPES]
        if invalid:
            return jsonify(error=f"unknown event types: {invalid}"), 400
        wh.events = json.dumps(data["events"])

    if "active" in data:
        wh.active = bool(data["active"])

    if "description" in data:
        wh.description = (data["description"] or "")[:255] or None

    db.session.commit()
    return jsonify(_wh_to_dict(wh))


@bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook(webhook_id: int):
    uid = int(get_jwt_identity())
    wh  = _get_or_404(webhook_id, uid)
    if not wh:
        return jsonify(error="not found"), 404
    db.session.delete(wh)
    db.session.commit()
    return jsonify(message="webhook deleted")


@bp.get("/<int:webhook_id>/deliveries")
@jwt_required()
def list_deliveries(webhook_id: int):
    uid = int(get_jwt_identity())
    wh  = _get_or_404(webhook_id, uid)
    if not wh:
        return jsonify(error="not found"), 404

    limit = min(int(request.args.get("limit", 20)), 100)
    deliveries = (
        db.session.query(WebhookDelivery)
        .filter_by(webhook_id=webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify([_delivery_to_dict(d) for d in deliveries])


@bp.post("/<int:webhook_id>/test")
@jwt_required()
def test_webhook(webhook_id: int):
    """Send a test ping event to verify the endpoint is reachable."""
    uid = int(get_jwt_identity())
    wh  = _get_or_404(webhook_id, uid)
    if not wh:
        return jsonify(error="not found"), 404

    count = dispatch_event(uid, "expense.created", {
        "test": True,
        "message": "This is a test delivery from FinMind",
        "webhook_id": webhook_id,
    })
    return jsonify({"dispatched": count, "webhook_id": webhook_id})


@bp.post("/retry")
@jwt_required()
def retry():
    """Trigger retry of all past-due failed deliveries for this user."""
    retried = retry_failed_deliveries()
    return jsonify({"retried": retried})
