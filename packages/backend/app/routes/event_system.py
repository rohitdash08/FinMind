from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.event_system import (
    get_event_history,
    get_event_stats,
    emit_budget_exceeded,
    emit_anomaly_detected,
    EventType,
)

bp = Blueprint("event_system", __name__)


@bp.route("/events", methods=["GET"])
@jwt_required()
def list_events():
    """
    GET /insights/events
    Query params:
      - event_type: filter by type (optional)
      - limit: max results (default 50, max 200)
      - offset: pagination offset (default 0)
    Returns paginated audit event history.
    """
    user_id = get_jwt_identity()
    event_type = request.args.get("event_type", None)
    try:
        limit = min(200, int(request.args.get("limit", 50)))
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "limit and offset must be integers"}), 400

    events = get_event_history(user_id, event_type, limit, offset)
    return jsonify({
        "events": events,
        "count": len(events),
        "limit": limit,
        "offset": offset,
    })


@bp.route("/events/stats", methods=["GET"])
@jwt_required()
def event_stats():
    """
    GET /insights/events/stats
    Returns count of events by type for the current user.
    """
    user_id = get_jwt_identity()
    stats = get_event_stats(user_id)
    return jsonify({"event_counts": stats})


@bp.route("/events/emit", methods=["POST"])
@jwt_required()
def emit_event():
    """
    POST /insights/events/emit
    Emit a manual event for testing/integration.
    Body: { "event_type": "budget_exceeded"|"anomaly_detected", "payload": {...} }
    """
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}
    event_type = body.get("event_type", "")
    payload = body.get("payload", {})

    if event_type == EventType.BUDGET_EXCEEDED:
        event_id = emit_budget_exceeded(
            user_id,
            payload.get("category", ""),
            float(payload.get("budget", 0)),
            float(payload.get("actual", 0)),
        )
    elif event_type == EventType.ANOMALY_DETECTED:
        event_id = emit_anomaly_detected(
            user_id,
            int(payload.get("expense_id", 0)),
            payload.get("reason", ""),
            float(payload.get("amount", 0)),
        )
    else:
        return jsonify({"error": f"Unsupported event_type: {event_type}"}), 400

    return jsonify({"event_id": event_id, "status": "emitted"})