"""
Webhook management routes.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json

from ..services.webhooks import (
    create_webhook,
    get_user_webhooks,
    delete_webhook,
    update_webhook,
    get_webhook_event_docs,
    emit_event as emit_webhook_event,
    deliver_webhook_events
)
from ..models import Webhook, WebhookEvent, db

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


@webhooks_bp.post("")
@jwt_required()
def create_webhook_handler():
    """Create a new webhook."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    url = data.get("url")
    events = data.get("events", [])
    
    if not url:
        return jsonify(error="URL is required"), 400
    
    if not events or not isinstance(events, list):
        return jsonify(error="Events must be a non-empty list"), 400
    
    try:
        webhook = create_webhook(user_id, url, events)
        return jsonify({
            "id": webhook.id,
            "url": webhook.url,
            "secret": webhook.secret,
            "events": json.loads(webhook.events),
            "active": webhook.active,
            "created_at": webhook.created_at.isoformat(),
            "updated_at": webhook.updated_at.isoformat()
        }), 201
    except Exception as e:
        return jsonify(error=str(e)), 500


@webhooks_bp.get("")
@jwt_required()
def list_webhooks():
    """List all webhooks for the current user."""
    user_id = get_jwt_identity()
    webhooks = get_user_webhooks(user_id)
    
    return jsonify([{
        "id": w.id,
        "url": w.url,
        "secret": w.secret,
        "events": json.loads(w.events),
        "active": w.active,
        "created_at": w.created_at.isoformat(),
        "updated_at": w.updated_at.isoformat()
    } for w in webhooks]), 200


@webhooks_bp.get("/<int:webhook_id>")
@jwt_required()
def get_webhook(webhook_id: int):
    """Get a specific webhook."""
    user_id = get_jwt_identity()
    webhook = Webhook.query.filter_by(id=webhook_id, user_id=user_id).first()
    
    if not webhook:
        return jsonify(error="Webhook not found"), 404
    
    return jsonify({
        "id": webhook.id,
        "url": webhook.url,
        "secret": webhook.secret,
        "events": json.loads(webhook.events),
        "active": webhook.active,
        "created_at": webhook.created_at.isoformat(),
        "updated_at": webhook.updated_at.isoformat()
    }), 200


@webhooks_bp.patch("/<int:webhook_id>")
@jwt_required()
def update_webhook_handler(webhook_id: int):
    """Update a webhook."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    updated = update_webhook(
        webhook_id,
        user_id,
        url=data.get("url"),
        events=data.get("events")
    )
    
    if not updated:
        return jsonify(error="Webhook not found"), 404
    
    return jsonify({
        "id": updated.id,
        "url": updated.url,
        "secret": updated.secret,
        "events": json.loads(updated.events),
        "active": updated.active,
        "created_at": updated.created_at.isoformat(),
        "updated_at": updated.updated_at.isoformat()
    }), 200


@webhooks_bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook_handler(webhook_id: int):
    """Delete a webhook."""
    user_id = get_jwt_identity()
    
    if not delete_webhook(webhook_id, user_id):
        return jsonify(error="Webhook not found"), 404
    
    return jsonify(message="Webhook deleted"), 200


@webhooks_bp.get("/<int:webhook_id>/events")
@jwt_required()
def list_webhook_events(webhook_id: int):
    """List events for a specific webhook."""
    user_id = get_jwt_identity()
    
    # Verify webhook belongs to user
    webhook = Webhook.query.filter_by(id=webhook_id, user_id=user_id).first()
    if not webhook:
        return jsonify(error="Webhook not found"), 404
    
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 50, type=int)
    
    if limit > 100:
        limit = 100
    
    offset = (page - 1) * limit
    
    events = WebhookEvent.query.filter_by(webhook_id=webhook_id).order_by(
        WebhookEvent.created_at.desc()
    ).offset(offset).limit(limit).all()
    
    total = WebhookEvent.query.filter_by(webhook_id=webhook_id).count()
    
    return jsonify({
        "events": [{
            "id": e.id,
            "event_type": e.event_type,
            "status": e.status,
            "delivery_attempts": e.delivery_attempts,
            "last_error": e.last_error,
            "created_at": e.created_at.isoformat(),
            "last_attempted_at": e.last_attempted_at.isoformat() if e.last_attempted_at else None,
            "delivered_at": e.delivered_at.isoformat() if e.delivered_at else None
        } for e in events],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }), 200


@webhooks_bp.get("/docs/events")
def get_event_docs():
    """Get documentation for supported webhook event types."""
    return jsonify(get_webhook_event_docs()), 200
