"""Cache management routes."""

from flask import Blueprint, jsonify, request
from app.services.smart_cache import get_cache

bp = Blueprint("cache", __name__)


@bp.route("/stats", methods=["GET"])
def cache_stats():
    """Get cache statistics."""
    return jsonify(get_cache().stats())


@bp.route("/invalidate", methods=["POST"])
def invalidate_cache():
    """Invalidate cache by event.

    Body: {"event": "expense_created", "user_id": 1}
    """
    data = request.get_json() or {}
    event = data.get("event")
    if not event:
        return jsonify({"error": "event is required"}), 400
    user_id = data.get("user_id")
    get_cache().invalidate(event, user_id=user_id)
    return jsonify({"ok": True, "event": event})


@bp.route("/clear", methods=["POST"])
def clear_cache():
    """Clear all cached data."""
    get_cache().clear_all()
    return jsonify({"ok": True})
