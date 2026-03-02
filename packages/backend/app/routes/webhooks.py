"""Webhook API routes."""
import secrets
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models_webhook import (
    WebhookSubscription,
    WebhookDelivery,
    WebhookEventType,
    WebhookStatus,
)
from app.services.webhook_service import trigger_event, verify_signature

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


def get_current_user_id() -> int:
    """Get current user ID from JWT."""
    return int(get_jwt_identity())


@webhooks_bp.route("", methods=["GET"])
@jwt_required()
def list_webhooks():
    """List all webhook subscriptions for current user."""
    user_id = get_current_user_id()
    subscriptions = WebhookSubscription.query.filter_by(user_id=user_id).all()
    return jsonify([sub.to_dict() for sub in subscriptions]), 200


@webhooks_bp.route("", methods=["POST"])
@jwt_required()
def create_webhook():
    """Create a new webhook subscription."""
    user_id = get_current_user_id()
    data = request.get_json()

    # Validation
    if not data or not data.get("url"):
        return jsonify({"error": "URL is required"}), 400

    if not data.get("events") or not isinstance(data["events"], list):
        return jsonify({"error": "Events array is required"}), 400

    # Validate event types
    valid_events = {e.value for e in WebhookEventType}
    invalid_events = set(data["events"]) - valid_events
    if invalid_events:
        return jsonify({
            "error": f"Invalid event types: {list(invalid_events)}",
            "valid_events": list(valid_events),
        }), 400

    # Create subscription
    subscription = WebhookSubscription(
        user_id=user_id,
        url=data["url"],
        secret=secrets.token_urlsafe(32),
        events=data["events"],
        description=data.get("description"),
    )

    try:
        db.session.add(subscription)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Failed to create webhook"}), 500

    response = subscription.to_dict()
    response["secret"] = subscription.secret  # Only show once on creation

    return jsonify(response), 201


@webhooks_bp.route("/<int:webhook_id>", methods=["GET"])
@jwt_required()
def get_webhook(webhook_id: int):
    """Get a specific webhook subscription."""
    user_id = get_current_user_id()
    subscription = WebhookSubscription.query.filter_by(
        id=webhook_id, user_id=user_id
    ).first()

    if not subscription:
        return jsonify({"error": "Webhook not found"}), 404

    return jsonify(subscription.to_dict()), 200


@webhooks_bp.route("/<int:webhook_id>", methods=["PUT"])
@jwt_required()
def update_webhook(webhook_id: int):
    """Update a webhook subscription."""
    user_id = get_current_user_id()
    subscription = WebhookSubscription.query.filter_by(
        id=webhook_id, user_id=user_id
    ).first()

    if not subscription:
        return jsonify({"error": "Webhook not found"}), 404

    data = request.get_json()

    if "url" in data:
        subscription.url = data["url"]
    if "events" in data:
        valid_events = {e.value for e in WebhookEventType}
        invalid_events = set(data["events"]) - valid_events
        if invalid_events:
            return jsonify({
                "error": f"Invalid event types: {list(invalid_events)}",
            }), 400
        subscription.events = data["events"]
    if "description" in data:
        subscription.description = data["description"]
    if "status" in data:
        try:
            subscription.status = WebhookStatus(data["status"])
        except ValueError:
            return jsonify({"error": "Invalid status"}), 400

    db.session.commit()
    return jsonify(subscription.to_dict()), 200


@webhooks_bp.route("/<int:webhook_id>", methods=["DELETE"])
@jwt_required()
def delete_webhook(webhook_id: int):
    """Delete a webhook subscription."""
    user_id = get_current_user_id()
    subscription = WebhookSubscription.query.filter_by(
        id=webhook_id, user_id=user_id
    ).first()

    if not subscription:
        return jsonify({"error": "Webhook not found"}), 404

    db.session.delete(subscription)
    db.session.commit()

    return jsonify({"message": "Webhook deleted successfully"}), 200


@webhooks_bp.route("/<int:webhook_id>/regenerate-secret", methods=["POST"])
@jwt_required()
def regenerate_secret(webhook_id: int):
    """Regenerate webhook secret."""
    user_id = get_current_user_id()
    subscription = WebhookSubscription.query.filter_by(
        id=webhook_id, user_id=user_id
    ).first()

    if not subscription:
        return jsonify({"error": "Webhook not found"}), 404

    subscription.secret = secrets.token_urlsafe(32)
    db.session.commit()

    return jsonify({
        "message": "Secret regenerated",
        "secret": subscription.secret,
    }), 200


@webhooks_bp.route("/<int:webhook_id>/deliveries", methods=["GET"])
@jwt_required()
def list_deliveries(webhook_id: int):
    """List delivery attempts for a webhook."""
    user_id = get_current_user_id()
    subscription = WebhookSubscription.query.filter_by(
        id=webhook_id, user_id=user_id
    ).first()

    if not subscription:
        return jsonify({"error": "Webhook not found"}), 404

    deliveries = WebhookDelivery.query.filter_by(
        subscription_id=webhook_id
    ).order_by(WebhookDelivery.created_at.desc()).limit(100).all()

    return jsonify([d.to_dict() for d in deliveries]), 200


@webhooks_bp.route("/events", methods=["GET"])
def list_event_types():
    """List all available webhook event types."""
    events = [
        {
            "type": e.value,
            "description": e.name.replace("_", " ").title(),
        }
        for e in WebhookEventType
    ]
    return jsonify(events), 200


@webhooks_bp.route("/test", methods=["POST"])
@jwt_required()
def test_webhook():
    """Send a test webhook event."""
    user_id = get_current_user_id()
    data = request.get_json()

    if not data or not data.get("url"):
        return jsonify({"error": "URL is required"}), 400

    # Send test event
    test_payload = {
        "message": "This is a test event from FinMind",
        "timestamp": datetime.utcnow().isoformat(),
    }

    trigger_event(
        user_id=user_id,
        event_type=WebhookEventType.EXPENSE_CREATED,
        payload=test_payload,
    )

    return jsonify({"message": "Test event triggered"}), 200
