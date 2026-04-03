"""Webhook management API routes."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.webhooks import (
    WebhookEventType,
    register_endpoint,
    delete_endpoint,
    emit_event,
)
from ..extensions import db
from ..models import WebhookEndpoint, WebhookDelivery

bp = Blueprint("webhooks", __name__)


@bp.get("/endpoints")
@jwt_required()
def list_endpoints():
    """List all webhook endpoints for the current user."""
    uid = int(get_jwt_identity())
    endpoints = WebhookEndpoint.query.filter_by(user_id=uid).all()
    return jsonify([
        {
            "id": ep.id,
            "url": ep.url,
            "description": ep.description,
            "active": ep.active,
            "created_at": ep.created_at.isoformat(),
        }
        for ep in endpoints
    ])


@bp.post("/endpoints")
@jwt_required()
def create_endpoint():
    """Register a new webhook endpoint."""
    uid = int(get_jwt_identity())
    body = request.get_json(force=True)
    url = body.get("url", "").strip()
    description = body.get("description", "").strip() or None

    if not url:
        return jsonify(error="url is required"), 400
    if not url.startswith(("https://", "http://")):
        return jsonify(error="url must start with https:// or http://"), 400

    endpoint = register_endpoint(uid, url, description)
    return jsonify(
        id=endpoint.id,
        url=endpoint.url,
        secret=endpoint.secret,  # Only returned on creation
        description=endpoint.description,
        active=endpoint.active,
        created_at=endpoint.created_at.isoformat(),
    ), 201


@bp.delete("/endpoints/<int:endpoint_id>")
@jwt_required()
def remove_endpoint(endpoint_id: int):
    """Delete a webhook endpoint."""
    uid = int(get_jwt_identity())
    if delete_endpoint(uid, endpoint_id):
        return "", 204
    return jsonify(error="endpoint not found"), 404


@bp.get("/endpoints/<int:endpoint_id>/deliveries")
@jwt_required()
def list_deliveries(endpoint_id: int):
    """List recent deliveries for an endpoint."""
    uid = int(get_jwt_identity())
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=uid).first()
    if not endpoint:
        return jsonify(error="endpoint not found"), 404

    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))

    pagination = (
        WebhookDelivery.query
        .filter_by(endpoint_id=endpoint_id)
        .order_by(WebhookDelivery.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        "items": [
            {
                "id": d.id,
                "event_type": d.event_type,
                "success": d.success,
                "status_code": d.status_code,
                "attempts": d.attempts,
                "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
                "created_at": d.created_at.isoformat(),
            }
            for d in pagination.items
        ],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
    })


@bp.get("/event-types")
@jwt_required()
def list_event_types():
    """List all available webhook event types."""
    return jsonify(event_types=[e.value for e in WebhookEventType])


@bp.post("/endpoints/<int:endpoint_id>/test")
@jwt_required()
def test_endpoint(endpoint_id: int):
    """Send a test event to an endpoint."""
    uid = int(get_jwt_identity())
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=uid).first()
    if not endpoint:
        return jsonify(error="endpoint not found"), 404

    emit_event(
        WebhookEventType.BUDGET_ALERT,
        data={"message": "Test webhook from FinMind", "test": True},
        user_id=uid,
    )
    return jsonify(message="Test event queued"), 200
