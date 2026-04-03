import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.events import emit, get_activity_feed, get_activity_summary, EventType

bp = Blueprint("events", __name__)
logger = logging.getLogger("finmind.events_routes")


@bp.get("/feed")
@jwt_required()
def activity_feed():
    """
    Get the user financial activity event feed.

    Query params:
        limit (int, 1-100, default 50): Number of events per page
        offset (int, default 0): Pagination offset
        event_type (str, optional): Filter by event type

    Returns:
        { "events": [...], "total": int, "limit": int, "offset": int }
    """
    uid = int(get_jwt_identity())
    try:
        limit = min(100, max(1, int(request.args.get("limit", 50))))
        offset = max(0, int(request.args.get("offset", 0)))
    except (ValueError, TypeError):
        return jsonify(error="limit and offset must be integers"), 400

    event_type = request.args.get("event_type")
    if event_type and event_type not in [e.value for e in EventType]:
        return jsonify(error=f"Unknown event_type: {event_type}"), 400

    result = get_activity_feed(uid, limit, offset, event_type)
    return jsonify(result)


@bp.get("/summary")
@jwt_required()
def activity_summary():
    """
    Get summary of financial activity for the past N days.

    Query params:
        days (int, 1-365, default 30): Period to summarize

    Returns:
        { "period_days": int, "total_events": int, "by_type": {...}, "most_active_type": str }
    """
    uid = int(get_jwt_identity())
    try:
        days = min(365, max(1, int(request.args.get("days", 30))))
    except (ValueError, TypeError):
        return jsonify(error="days must be an integer between 1 and 365"), 400

    result = get_activity_summary(uid, days)
    return jsonify(result)


@bp.post("/emit")
@jwt_required()
def emit_event():
    """
    Manually emit a financial event (for testing or custom integrations).

    Body: {
        "event_type": "expense_added" | "bill_paid" | ...,
        "payload": {...}
    }
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    event_type = (data.get("event_type") or "").strip()
    payload = data.get("payload", {})

    if not event_type:
        return jsonify(error="event_type is required"), 400

    valid_types = [e.value for e in EventType]
    if event_type not in valid_types:
        return jsonify(error=f"event_type must be one of: {valid_types}"), 400

    if not isinstance(payload, dict):
        return jsonify(error="payload must be an object"), 400

    event = emit(uid, event_type, payload)
    logger.info("Manual event emitted uid=%s type=%s", uid, event_type)
    return jsonify(
        id=event.id if event else None,
        event_type=event_type,
        occurred_at=event.occurred_at.isoformat() if event else None,
    ), 201
