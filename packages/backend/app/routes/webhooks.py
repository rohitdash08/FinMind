"""
Webhook management routes.

Provides endpoints for users to manage their webhook subscriptions.
"""

import json
import secrets

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import WebhookEvent, WebhookSubscription
from ..services.webhook import verify_webhook_signature

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")

# Supported event types (exposed for documentation)
SUPPORTED_EVENTS = [e.value for e in WebhookEvent]


@bp.get("")
@jwt_required()
def list_subscriptions():
    """List all webhook subscriptions for the current user."""
    uid = int(get_jwt_identity())
    subs = (
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
                "events": json.loads(s.events or "[]"),
                "active": s.active,
                "created_at": s.created_at.isoformat(),
            }
            for s in subs
        ]
    )


@bp.post("")
@jwt_required()
def create_subscription():
    """
    Create a new webhook subscription.
    
    Request body:
    {
        "url": "https://example.com/webhook",
        "events": ["expense.created", "expense.updated"]
    }
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    url = data.get("url", "").strip()
    if not url:
        return jsonify(error="url is required"), 400
    if not url.startswith(("http://", "https://")):
        return jsonify(error="url must be http or https"), 400

    events = data.get("events", [])
    if not isinstance(events, list) or not events:
        return jsonify(error="events must be a non-empty list"), 400

    # Validate event types
    invalid = [e for e in events if e not in SUPPORTED_EVENTS]
    if invalid:
        return jsonify(error=f"invalid event types: {invalid}"), 400

    # Generate a secure random secret
    secret = secrets.token_urlsafe(32)

    sub = WebhookSubscription(
        user_id=uid,
        url=url,
        secret=secret,
        events=json.dumps(events),
        active=True,
    )
    db.session.add(sub)
    db.session.commit()

    return jsonify(
        {
            "id": sub.id,
            "url": sub.url,
            "events": events,
            "secret": secret,  # Only shown once at creation
            "active": sub.active,
            "created_at": sub.created_at.isoformat(),
        }
    ), 201


@bp.get("/<int:sub_id>")
@jwt_required()
def get_subscription(sub_id: int):
    """Get a specific webhook subscription."""
    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(
        {
            "id": sub.id,
            "url": sub.url,
            "events": json.loads(sub.events or "[]"),
            "active": sub.active,
            "created_at": sub.created_at.isoformat(),
        }
    )


@bp.patch("/<int:sub_id>")
@jwt_required()
def update_subscription(sub_id: int):
    """Update a webhook subscription (events, active status)."""
    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "url" in data:
        url = data["url"].strip()
        if not url or not url.startswith(("http://", "https://")):
            return jsonify(error="invalid url"), 400
        sub.url = url

    if "events" in data:
        events = data["events"]
        if not isinstance(events, list) or not events:
            return jsonify(error="events must be a non-empty list"), 400
        invalid = [e for e in events if e not in SUPPORTED_EVENTS]
        if invalid:
            return jsonify(error=f"invalid event types: {invalid}"), 400
        sub.events = json.dumps(events)

    if "active" in data:
        sub.active = bool(data["active"])

    db.session.commit()
    return jsonify(
        {
            "id": sub.id,
            "url": sub.url,
            "events": json.loads(sub.events or "[]"),
            "active": sub.active,
            "created_at": sub.created_at.isoformat(),
        }
    )


@bp.delete("/<int:sub_id>")
@jwt_required()
def delete_subscription(sub_id: int):
    """Delete a webhook subscription."""
    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(sub)
    db.session.commit()
    return jsonify(message="deleted")


@bp.post("/<int:sub_id>/rotate-secret")
@jwt_required()
def rotate_secret(sub_id: int):
    """Rotate the webhook signing secret."""
    import secrets as _secrets

    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404

    sub.secret = _secrets.token_urlsafe(32)
    db.session.commit()
    return jsonify(
        {
            "id": sub.id,
            "secret": sub.secret,
        }
    )


@bp.get("/events")
@jwt_required()
def list_event_types():
    """List all supported webhook event types."""
    return jsonify(
        {
            "events": SUPPORTED_EVENTS,
            "descriptions": {
                "expense.created": "Fired when a new expense is created",
                "expense.updated": "Fired when an expense is modified",
                "expense.deleted": "Fired when an expense is deleted",
                "bill.due": "Fired when a bill is due",
                "reminder.sent": "Fired when a reminder is sent",
            },
        }
    )
