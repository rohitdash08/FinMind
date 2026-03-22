"""Cache administration endpoints for monitoring and management."""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.smart_cache import get_cache_stats, clear_user_cache, CACHE_TTL

bp = Blueprint("cache_admin", __name__)


@bp.get("/stats")
@jwt_required()
def cache_stats():
    """Get cache hit/miss statistics."""
    stats = get_cache_stats()
    return jsonify({
        "stats": stats,
        "ttl_policies": CACHE_TTL,
    })


@bp.delete("/clear")
@jwt_required()
def clear_cache():
    """Clear all caches for the current user."""
    uid = int(get_jwt_identity())
    clear_user_cache(uid)
    return jsonify({"message": "Cache cleared", "user_id": uid}), 200
