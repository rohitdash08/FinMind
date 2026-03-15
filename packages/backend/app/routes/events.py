"""Event-Driven Financial Activity routes.

Endpoints:
  POST   /events/emit          — emit a custom event
  GET    /events               — list events (filtered, paginated)
  GET    /events/<id>          — get single event
  GET    /events/replay        — replay events in chronological order
  GET    /events/stats         — event analytics
  GET    /events/types         — list available event types
  POST   /events/subscribe     — subscribe to event type
  DELETE /events/subscribe/<id>— unsubscribe
  GET    /events/subscriptions — list subscriptions
"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.events import (
    emit_event,
    get_events,
    get_event_by_id,
    replay_events,
    event_stats,
    subscribe,
    unsubscribe,
    list_subscriptions,
    available_event_types,
)

bp = Blueprint("events", __name__)


@bp.route("/emit", methods=["POST"])
@jwt_required()
def emit():
    """Emit a financial event."""
    uid = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    event_type = data.get("event_type")
    entity_type = data.get("entity_type")

    if not event_type or not entity_type:
        return jsonify({"error": "event_type and entity_type are required"}), 400

    result = emit_event(
        user_id=uid,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=data.get("entity_id"),
        payload=data.get("payload", {}),
        metadata=data.get("metadata", {}),
    )
    return jsonify(result), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_events():
    """List events with filtering and pagination."""
    uid = get_jwt_identity()

    event_type = request.args.get("event_type")
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id", type=int)
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    since = None
    if request.args.get("since"):
        try:
            since = datetime.fromisoformat(request.args["since"])
        except ValueError:
            return jsonify({"error": "Invalid since format"}), 400

    until = None
    if request.args.get("until"):
        try:
            until = datetime.fromisoformat(request.args["until"])
        except ValueError:
            return jsonify({"error": "Invalid until format"}), 400

    result = get_events(
        user_id=uid,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        since=since,
        until=until,
        limit=min(limit, 200),
        offset=offset,
    )
    return jsonify(result), 200


@bp.route("/<int:event_id>", methods=["GET"])
@jwt_required()
def get_event(event_id: int):
    """Get a single event."""
    uid = get_jwt_identity()
    result = get_event_by_id(uid, event_id)
    if not result:
        return jsonify({"error": "Event not found"}), 404
    return jsonify(result), 200


@bp.route("/replay", methods=["GET"])
@jwt_required()
def replay():
    """Replay events in chronological order."""
    uid = get_jwt_identity()
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id", type=int)

    since = None
    if request.args.get("since"):
        try:
            since = datetime.fromisoformat(request.args["since"])
        except ValueError:
            return jsonify({"error": "Invalid since format"}), 400

    events = replay_events(uid, entity_type, entity_id, since)
    return jsonify({"events": events, "count": len(events)}), 200


@bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    """Event analytics and statistics."""
    uid = get_jwt_identity()
    days = request.args.get("days", 30, type=int)
    result = event_stats(uid, days=min(days, 365))
    return jsonify(result), 200


@bp.route("/types", methods=["GET"])
@jwt_required()
def event_types():
    """List all available event types."""
    return jsonify(available_event_types()), 200


@bp.route("/subscribe", methods=["POST"])
@jwt_required()
def subscribe_to_event():
    """Subscribe to an event type."""
    uid = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    event_type = data.get("event_type")
    if not event_type:
        return jsonify({"error": "event_type is required"}), 400

    result = subscribe(
        user_id=uid,
        event_type=event_type,
        callback_type=data.get("callback_type", "internal"),
        callback_url=data.get("callback_url"),
    )
    return jsonify(result), 201


@bp.route("/subscribe/<int:sub_id>", methods=["DELETE"])
@jwt_required()
def unsubscribe_from_event(sub_id: int):
    """Unsubscribe from an event."""
    uid = get_jwt_identity()
    if unsubscribe(uid, sub_id):
        return jsonify({"message": "Unsubscribed"}), 200
    return jsonify({"error": "Subscription not found"}), 404


@bp.route("/subscriptions", methods=["GET"])
@jwt_required()
def subscriptions():
    """List active subscriptions."""
    uid = get_jwt_identity()
    active = request.args.get("active", "true").lower() == "true"
    return jsonify(list_subscriptions(uid, active_only=active)), 200
