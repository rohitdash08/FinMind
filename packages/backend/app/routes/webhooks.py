import json
import secrets
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import WebhookDelivery, WebhookEndpoint, WebhookEvent
from ..services.webhooks import get_delivery_stats, retry_failed_webhooks

bp = Blueprint("webhooks", __name__)


@bp.get("")
@jwt_required()
def list_webhooks():
    """List all webhook endpoints for current user"""
    uid = int(get_jwt_identity())
    endpoints = (
        db.session.query(WebhookEndpoint)
        .filter_by(user_id=uid)
        .order_by(WebhookEndpoint.created_at.desc())
        .all()
    )
    return jsonify([_endpoint_to_dict(e) for e in endpoints])


@bp.post("")
@jwt_required()
def create_webhook():
    """Create a new webhook endpoint"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    url = data.get("url", "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return jsonify(error="valid URL required"), 400

    events = data.get("events", [])
    if not isinstance(events, list) or not events:
        return jsonify(error="events array required"), 400

    secret = secrets.token_urlsafe(32)

    endpoint = WebhookEndpoint(
        user_id=uid,
        url=url,
        secret=secret,
        events=json.dumps(events),
        active=data.get("active", True),
    )
    db.session.add(endpoint)
    db.session.commit()

    return jsonify(_endpoint_to_dict(endpoint)), 201


@bp.get("/<int:webhook_id>")
@jwt_required()
def get_webhook(webhook_id: int):
    """Get a specific webhook endpoint"""
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, webhook_id)

    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404

    return jsonify(_endpoint_to_dict(endpoint))


@bp.patch("/<int:webhook_id>")
@jwt_required()
def update_webhook(webhook_id: int):
    """Update a webhook endpoint"""
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, webhook_id)

    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "url" in data:
        url = data["url"].strip()
        if not url or not url.startswith(("http://", "https://")):
            return jsonify(error="valid URL required"), 400
        endpoint.url = url

    if "events" in data:
        events = data["events"]
        if not isinstance(events, list) or not events:
            return jsonify(error="events array required"), 400
        endpoint.events = json.dumps(events)

    if "active" in data:
        endpoint.active = bool(data["active"])

    endpoint.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_endpoint_to_dict(endpoint))


@bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook(webhook_id: int):
    """Delete a webhook endpoint"""
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, webhook_id)

    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(endpoint)
    db.session.commit()

    return "", 204


@bp.post("/<int:webhook_id>/regenerate-secret")
@jwt_required()
def regenerate_secret(webhook_id: int):
    """Regenerate webhook secret"""
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, webhook_id)

    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404

    endpoint.secret = secrets.token_urlsafe(32)
    endpoint.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_endpoint_to_dict(endpoint))


@bp.get("/events")
@jwt_required()
def list_events():
    """List webhook events for current user"""
    uid = int(get_jwt_identity())

    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(100, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    event_type = request.args.get("type")
    query = db.session.query(WebhookEvent).filter_by(user_id=uid)

    if event_type:
        query = query.filter_by(event_type=event_type)

    events = (
        query.order_by(WebhookEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return jsonify([_event_to_dict(e) for e in events])


@bp.get("/events/<int:event_id>/deliveries")
@jwt_required()
def list_deliveries(event_id: int):
    """List deliveries for a specific event"""
    uid = int(get_jwt_identity())
    event = db.session.get(WebhookEvent, event_id)

    if not event or event.user_id != uid:
        return jsonify(error="not found"), 404

    deliveries = (
        db.session.query(WebhookDelivery)
        .filter_by(event_id=event_id)
        .order_by(WebhookDelivery.created_at.desc())
        .all()
    )

    return jsonify([_delivery_to_dict(d) for d in deliveries])


@bp.post("/retry")
@jwt_required()
def retry_webhooks():
    """Manually trigger retry of failed webhooks"""
    uid = int(get_jwt_identity())
    count = retry_failed_webhooks()
    return jsonify({"retried": count})


@bp.get("/stats")
@jwt_required()
def get_stats():
    """Get webhook delivery statistics"""
    uid = int(get_jwt_identity())
    stats = get_delivery_stats(uid)
    return jsonify(stats)


def _endpoint_to_dict(endpoint: WebhookEndpoint) -> dict:
    """Convert WebhookEndpoint to dictionary"""
    try:
        events = json.loads(endpoint.events)
    except (json.JSONDecodeError, TypeError):
        events = []

    return {
        "id": endpoint.id,
        "url": endpoint.url,
        "secret": endpoint.secret,
        "events": events,
        "active": endpoint.active,
        "created_at": endpoint.created_at.isoformat(),
        "updated_at": endpoint.updated_at.isoformat(),
    }


def _event_to_dict(event: WebhookEvent) -> dict:
    """Convert WebhookEvent to dictionary"""
    try:
        payload = json.loads(event.payload)
    except (json.JSONDecodeError, TypeError):
        payload = {}

    return {
        "id": event.id,
        "type": event.event_type.value,
        "payload": payload,
        "created_at": event.created_at.isoformat(),
    }


def _delivery_to_dict(delivery: WebhookDelivery) -> dict:
    """Convert WebhookDelivery to dictionary"""
    return {
        "id": delivery.id,
        "endpoint_id": delivery.endpoint_id,
        "event_id": delivery.event_id,
        "status": delivery.status.value,
        "attempt_count": delivery.attempt_count,
        "last_attempt_at": (
            delivery.last_attempt_at.isoformat() if delivery.last_attempt_at else None
        ),
        "next_retry_at": (
            delivery.next_retry_at.isoformat() if delivery.next_retry_at else None
        ),
        "response_status": delivery.response_status,
        "error_message": delivery.error_message,
        "created_at": delivery.created_at.isoformat(),
        "completed_at": (
            delivery.completed_at.isoformat() if delivery.completed_at else None
        ),
    }
