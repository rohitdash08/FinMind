"""
Webhook management routes.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db

bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


@bp.route("", methods=["GET"])
@jwt_required()
def get_webhook_config():
    """
    Get current webhook configuration for the user.
    """
    from ..services.webhooks import get_webhook_manager

    manager = get_webhook_manager()
    from flask import current_app

    return jsonify(
        {
            "enabled": manager.enabled,
            "webhook_url": manager.settings.webhook_url,
            "has_secret": bool(manager.settings.webhook_secret),
        }
    )


@bp.route("/test", methods=["POST"])
@jwt_required()
def test_webhook():
    """
    Send a test webhook to verify configuration.
    """
    from ..services.webhooks import WebhookDelivery, get_webhook_manager

    manager = get_webhook_manager()
    if not manager.enabled:
        return jsonify(error="webhook not configured"), 400

    data = request.get_json() or {}
    custom_url = data.get("webhook_url")

    delivery = WebhookDelivery(
        event_type="test",
        payload={
            "message": "This is a test webhook from FinMind",
            "user_id": get_jwt_identity(),
        },
        webhook_url=custom_url or manager.settings.webhook_url,
        secret=manager.settings.webhook_secret,
        timeout=manager.settings.webhook_timeout,
        max_retries=manager.settings.webhook_max_retries,
    )

    success = delivery.deliver()

    return jsonify(
        {
            "success": success,
            "delivery_id": delivery.delivery_id,
            "attempts": delivery.attempts,
            "status": delivery.response_status,
            "error": delivery.error,
        }
    )


@bp.route("/events", methods=["GET"])
@jwt_required()
def list_event_types():
    """
    List all available webhook event types.
    """
    from ..services.webhooks import WebhookEventType

    return jsonify(
        {
            "events": [
                {
                    "type": event.value,
                    "description": _get_event_description(event),
                }
                for event in WebhookEventType
            ]
        }
    )


def _get_event_description(event_type: WebhookEventType) -> str:
    """Get human-readable description for event type."""
    descriptions = {
        "expense.created": "Triggered when a new expense is created",
        "expense.updated": "Triggered when an expense is updated",
        "expense.deleted": "Triggered when an expense is deleted",
        "bill.created": "Triggered when a new bill is created",
        "bill.updated": "Triggered when a bill is updated",
        "bill.deleted": "Triggered when a bill is deleted",
        "bill.due_soon": "Triggered when a bill is due within 3 days",
        "bill.overdue": "Triggered when a bill is past due date",
        "category.created": "Triggered when a new category is created",
        "category.updated": "Triggered when a category is updated",
        "category.deleted": "Triggered when a category is deleted",
        "reminder.sent": "Triggered when a reminder is sent",
        "user.created": "Triggered when a new user registers",
    }
    return descriptions.get(event_type.value, "Custom webhook event")
