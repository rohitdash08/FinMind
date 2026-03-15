"""Routes for smart caching management and monitoring."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.smart_cache import (
    get_cache_stats,
    reset_cache_stats,
    cache_get,
    cache_set,
    cache_delete,
    cache_invalidate_user,
    cache_invalidate_all,
    warm_cache_for_user,
    _make_cache_key,
    _l1_cache,
    CACHE_POLICIES,
)

bp = Blueprint("smart_cache", __name__)


@bp.route("/stats", methods=["GET"])
@jwt_required()
def cache_stats():
    """Get comprehensive cache statistics.

    Returns L1 (memory) and L2 (Redis) cache metrics,
    including hit rates, sizes, and policy configuration.
    """
    user_id = int(get_jwt_identity())
    stats = get_cache_stats()
    return jsonify(stats), 200


@bp.route("/stats/reset", methods=["POST"])
@jwt_required()
def reset_stats():
    """Reset cache statistics counters."""
    user_id = int(get_jwt_identity())
    reset_cache_stats()
    return jsonify({"message": "Cache statistics reset"}), 200


@bp.route("/policies", methods=["GET"])
@jwt_required()
def list_policies():
    """List all cache TTL policies.

    Shows the TTL and prefix for each data type.
    """
    user_id = int(get_jwt_identity())
    policies = {
        name: {
            "ttl_seconds": p["ttl"],
            "ttl_human": _format_ttl(p["ttl"]),
            "prefix": p["prefix"],
        }
        for name, p in CACHE_POLICIES.items()
    }
    return jsonify({"policies": policies, "count": len(policies)}), 200


@bp.route("/invalidate/user", methods=["POST"])
@jwt_required()
def invalidate_user_cache():
    """Invalidate all cached data for the current user.

    Optional JSON body:
    - data_types: list of data types to invalidate (default: all)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    data_types = data.get("data_types")

    cache_invalidate_user(user_id, data_types)
    return jsonify({
        "message": "Cache invalidated",
        "user_id": user_id,
        "data_types": data_types or "all",
    }), 200


@bp.route("/invalidate/all", methods=["POST"])
@jwt_required()
def invalidate_all():
    """Invalidate entire application cache (admin operation)."""
    user_id = int(get_jwt_identity())
    cache_invalidate_all()
    return jsonify({"message": "All caches invalidated"}), 200


@bp.route("/warm", methods=["POST"])
@jwt_required()
def warm_cache():
    """Warm cache for the current user.

    Pre-populates frequently accessed data.
    """
    user_id = int(get_jwt_identity())

    # Define default warmers (simplified — in production these would call actual services)
    results = warm_cache_for_user(user_id)
    return jsonify({
        "message": "Cache warming completed",
        "user_id": user_id,
        "results": results,
    }), 200


@bp.route("/test", methods=["POST"])
@jwt_required()
def test_cache():
    """Test cache operations (set, get, delete).

    Accepts JSON body:
    - key: string (required)
    - value: any (required for set)
    - operation: 'set' | 'get' | 'delete' (default 'set')
    - ttl: int seconds (default 300)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    operation = data.get("operation", "set")
    key = data.get("key")

    if not key:
        return jsonify({"error": "key is required"}), 400

    # Scope the key to the user
    full_key = f"test:user:{user_id}:{key}"

    if operation == "set":
        value = data.get("value")
        if value is None:
            return jsonify({"error": "value is required for set"}), 400
        ttl = data.get("ttl", 300)
        cache_set(full_key, value, ttl)
        return jsonify({"message": "Cached", "key": full_key, "ttl": ttl}), 200

    elif operation == "get":
        value = cache_get(full_key)
        return jsonify({
            "key": full_key,
            "value": value,
            "found": value is not None,
        }), 200

    elif operation == "delete":
        cache_delete(full_key)
        return jsonify({"message": "Deleted", "key": full_key}), 200

    return jsonify({"error": f"Unknown operation: {operation}"}), 400


@bp.route("/health", methods=["GET"])
@jwt_required()
def cache_health():
    """Check cache health and connectivity."""
    user_id = int(get_jwt_identity())

    l1_ok = True
    l2_ok = False

    try:
        from app.extensions import redis_client
        redis_client.ping()
        l2_ok = True
    except Exception:
        pass

    return jsonify({
        "l1_cache": {"status": "healthy" if l1_ok else "degraded"},
        "l2_cache": {"status": "healthy" if l2_ok else "degraded"},
        "overall": "healthy" if l1_ok else "degraded",
    }), 200


def _format_ttl(seconds: int) -> str:
    """Format TTL seconds to human-readable string."""
    if seconds >= 3600:
        hours = seconds // 3600
        return f"{hours}h"
    elif seconds >= 60:
        minutes = seconds // 60
        return f"{minutes}m"
    return f"{seconds}s"
