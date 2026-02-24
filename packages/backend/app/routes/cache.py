"""API routes for cache management (#127)."""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.cache import cache_stats, invalidate_user, clear_all

bp = Blueprint("cache", __name__)


@bp.get("/stats")
@jwt_required()
def stats():
    """Get cache statistics."""
    return jsonify(cache_stats())


@bp.post("/invalidate")
@jwt_required()
def invalidate():
    """Invalidate current user's cache."""
    uid = get_jwt_identity()
    invalidate_user(uid)
    return jsonify(status="invalidated", user_id=uid)


@bp.post("/clear")
@jwt_required()
def clear():
    """Clear entire cache (admin)."""
    clear_all()
    return jsonify(status="cleared")
