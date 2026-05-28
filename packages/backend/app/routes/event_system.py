"""Event-Driven Financial Activity API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.event_system import EventBus, Event, EventType, event_bus

bp = Blueprint("event_system", __name__)


@bp.post("/publish")
@jwt_required()
def publish_event():
    """Publish a financial event."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}

    event = Event(
        event_type=data.get("event_type", ""),
        payload=data.get("payload", {}),
        user_id=user_id,
        source=data.get("source", "api"),
    )

    result = event_bus.publish(event)
    return jsonify(result)


@bp.get("/log")
@jwt_required()
def get_event_log():
    """Get event log for current user."""
    user_id = str(get_jwt_identity())
    event_type = request.args.get("event_type")
    limit = int(request.args.get("limit", 50))

    events = event_bus.get_event_log(event_type=event_type, user_id=user_id, limit=limit)
    return jsonify({"events": events, "count": len(events)})


@bp.post("/subscribe")
@jwt_required()
def subscribe_handler():
    """Register a webhook for events."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}

    event_type = data.get("event_type", "")
    webhook_url = data.get("webhook_url", "")

    if not event_type or not webhook_url:
        return jsonify({"error": "event_type and webhook_url required"}), 400

    def webhook_handler(event):
        return {"webhook": webhook_url, "event": event.event_id}

    event_bus.subscribe(event_type, webhook_handler, name=f"webhook_{user_id}_{event_type}")
    return jsonify({"status": "subscribed", "event_type": event_type})


@bp.post("/replay")
@jwt_required()
def replay_events():
    """Replay events (admin/debug)."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}

    result = event_bus.replay(
        event_type=data.get("event_type"),
        user_id=user_id,
    )
    return jsonify(result)
