"""
Webhook Routes for FinMind

Provides endpoints for:
- Registering webhook subscriptions
- Triggering webhook delivery
- Managing webhooks
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Webhook, User, WebhookDelivery, WebhookDeliveryStatus
from ..services.webhooks import webhook_service, WebhookEventType
import logging

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks")


@bp.get("")
@jwt_required()
def list_webhooks():
    """List all webhooks for the current user"""
    uid = int(get_jwt_identity())
    webhooks = db.session.query(Webhook).filter_by(user_id=uid).order_by(
        Webhook.created_at.desc()
    ).all()
    return jsonify([_webhook_to_dict(w) for w in webhooks])


@bp.post("")
@jwt_required()
def create_webhook():
    """Register a new webhook subscription"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    url = data.get("url")
    if not url:
        return jsonify(error="url is required"), 400

    if not url.startswith(("http://", "https://")):
        return jsonify(error="url must start with http:// or https://"), 400

    # Validate events if provided
    events = data.get("events")
    if events is not None:
        valid_events = [e.value for e in WebhookEventType]
        invalid_events = [e for e in events if e not in valid_events]
        if invalid_events:
            return jsonify(
                error=f"Invalid events: {', '.join(invalid_events)}. "
                f"Valid events: {', '.join(valid_events)}"
            ), 400

    webhook = Webhook(
        user_id=uid,
        url=url,
        secret=data.get("secret"),
        events=events,
        active=True,
    )
    db.session.add(webhook)
    db.session.commit()

    logger.info("Created webhook id=%s for user=%s url=%s events=%s", webhook.id, uid, url, events)
    return jsonify(_webhook_to_dict(webhook)), 201


@bp.get("/events")
def list_available_events():
    """List all available webhook event types"""
    events = [
        {"type": e.value, "description": e.value.replace(".", " ").title()}
        for e in WebhookEventType
    ]
    return jsonify(events)


@bp.get("/deliveries/<int:webhook_id>")
@jwt_required()
def list_webhook_deliveries(webhook_id: int):
    """List delivery records for a specific webhook"""
    uid = int(get_jwt_identity())

    # Verify webhook belongs to user
    webhook = db.session.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != uid:
        return jsonify(error="not found"), 404

    # Get delivery records (simplified - in production you'd paginate)
    deliveries = db.session.query(WebhookDelivery).filter_by(
        webhook_id=webhook_id
    ).order_by(WebhookDelivery.last_attempt_at.desc()).limit(100).all()

    return jsonify([_delivery_to_dict(d) for d in deliveries])


@bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook(webhook_id: int):
    """Delete a webhook subscription"""
    uid = int(get_jwt_identity())

    webhook = db.session.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(webhook)
    db.session.commit()

    logger.info("Deleted webhook id=%s for user=%s", webhook_id, uid)
    return jsonify(message="webhook deleted")


@bp.post("/test")
@jwt_required()
def test_webhook():
    """Test webhook delivery with a sample event"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    webhook_id = data.get("webhook_id")
    if not webhook_id:
        return jsonify(error="webhook_id is required"), 400

    webhook = db.session.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != uid:
        return jsonify(error="not found"), 404

    # Emit a test expense created event
    test_expense = {
        "id": 99999,
        "amount": 100.0,
        "currency": "USD",
        "expense_type": "EXPENSE",
        "description": "Test webhook event",
        "date": "2026-03-05",
        "category_id": 1,
    }

    payload = webhook_service._build_payload(
        WebhookEventType.EXPENSE_CREATED,
        test_expense,
        uid
    )

    success = webhook_service._deliver_webhook(payload)
    return jsonify({
        "success": success,
        "message": "Test webhook delivered" if success else "Test webhook failed"
    })


def _webhook_to_dict(w: Webhook) -> dict:
    """Convert Webhook model to dict"""
    return {
        "id": w.id,
        "url": w.url,
        "secret": w.secret[:8] + "..." if w.secret else None,  # Mask secret
        "events": w.events,
        "active": w.active,
        "created_at": w.created_at.isoformat(),
        "last_delivered_at": w.last_delivered_at.isoformat() if w.last_delivered_at else None,
    }


def _delivery_to_dict(d: WebhookDelivery) -> dict:
    """Convert WebhookDelivery model to dict"""
    return {
        "id": d.id,
        "webhook_id": d.webhook_id,
        "event_type": d.event_type,
        "status": d.status,
        "response_status": d.response_status,
        "error_message": d.error_message,
        "retry_count": d.retry_count,
        "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
        "created_at": d.created_at.isoformat(),
    }
