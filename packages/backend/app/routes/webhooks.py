"""
Webhook management API routes.

Provides endpoints for:
  - Registering/unregistering webhook endpoints
  - Listing endpoints and delivery history
  - Retrying failed deliveries
  - Listing supported event types
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..services.webhooks import (
    DeliveryStatus,
    EventType,
    webhook_manager,
)

bp = Blueprint("webhooks", __name__)


@bp.route("/event-types", methods=["GET"])
@jwt_required()
def list_event_types():
    """List all supported webhook event types."""
    return jsonify({
        "event_types": [
            {"name": e.value, "description": e.name.replace("_", " ").title()}
            for e in EventType
        ]
    }), 200


@bp.route("/endpoints", methods=["GET"])
@jwt_required()
def list_endpoints():
    """List all registered webhook endpoints."""
    endpoints = webhook_manager.list_endpoints()
    return jsonify({
        "endpoints": [
            {
                "id": ep.id,
                "url": ep.url,
                "events": ep.events,
                "active": ep.active,
                "created_at": ep.created_at.isoformat(),
            }
            for ep in endpoints
        ]
    }), 200


@bp.route("/endpoints", methods=["POST"])
@jwt_required()
def register_endpoint():
    """
    Register a new webhook endpoint.

    JSON body:
        url: str (required) — delivery URL
        secret: str (required) — shared secret for HMAC signing
        events: list[str] (optional) — event types to subscribe to
    """
    data = request.get_json() or {}

    url = data.get("url")
    secret = data.get("secret")

    if not url or not secret:
        return jsonify({"error": "url and secret are required"}), 400

    events = data.get("events")
    if events:
        valid_events = {e.value for e in EventType}
        invalid = [e for e in events if e not in valid_events]
        if invalid:
            return jsonify({
                "error": f"Invalid event types: {invalid}",
                "valid_types": list(valid_events),
            }), 400

    endpoint = webhook_manager.register_endpoint(
        url=url,
        secret=secret,
        events=events,
        metadata=data.get("metadata"),
    )

    return jsonify({
        "id": endpoint.id,
        "url": endpoint.url,
        "events": endpoint.events,
        "active": endpoint.active,
        "created_at": endpoint.created_at.isoformat(),
    }), 201


@bp.route("/endpoints/<endpoint_id>", methods=["DELETE"])
@jwt_required()
def unregister_endpoint(endpoint_id):
    """Unregister a webhook endpoint."""
    success = webhook_manager.unregister_endpoint(endpoint_id)
    if not success:
        return jsonify({"error": "Endpoint not found"}), 404
    return jsonify({"success": True}), 200


@bp.route("/deliveries", methods=["GET"])
@jwt_required()
def list_deliveries():
    """
    List webhook delivery history.

    Query params:
        endpoint_id: Filter by endpoint
        status: Filter by status (pending, success, failed, retrying)
        limit: Max results (default 50)
    """
    endpoint_id = request.args.get("endpoint_id")
    status_str = request.args.get("status")
    limit = int(request.args.get("limit", 50))

    status = None
    if status_str:
        try:
            status = DeliveryStatus(status_str)
        except ValueError:
            return jsonify({"error": f"Invalid status: {status_str}"}), 400

    deliveries = webhook_manager.get_deliveries(
        endpoint_id=endpoint_id,
        status=status,
        limit=limit,
    )

    return jsonify({
        "deliveries": [
            {
                "id": d.id,
                "endpoint_id": d.endpoint_id,
                "event_type": d.event_type,
                "status": d.status.value,
                "status_code": d.status_code,
                "attempts": d.attempts,
                "created_at": d.created_at.isoformat(),
                "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
                "error": d.error,
            }
            for d in deliveries
        ]
    }), 200


@bp.route("/retry", methods=["POST"])
@jwt_required()
def retry_failed():
    """Retry all failed webhook deliveries."""
    retried = webhook_manager.retry_failed()
    return jsonify({
        "retried": len(retried),
        "deliveries": [
            {
                "id": d.id,
                "event_type": d.event_type,
                "status": d.status.value,
                "attempts": d.attempts,
            }
            for d in retried
        ]
    }), 200
