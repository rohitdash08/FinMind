"""
cache_management.py — Cache statistics and manual bust endpoints.

GET  /cache/stats          — global hit/miss stats (JWT required)
POST /cache/bust           — clear all cached data for the current user
"""
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.cache import cache_stats, invalidate_user_caches

bp_cache = Blueprint("cache_mgmt", __name__)
logger = logging.getLogger("finmind.cache_mgmt")


@bp_cache.get("/stats")
@jwt_required()
def get_cache_stats():
    """
    Return cache hit/miss statistics.
    Optionally includes per-user key count when ?user=true.
    """
    uid = int(get_jwt_identity())
    include_user = request.args.get("user", "false").lower() == "true"
    stats = cache_stats(uid=uid if include_user else None)
    return jsonify(stats)


@bp_cache.post("/bust")
@jwt_required()
def bust_user_cache():
    """
    Invalidate all cached data for the current user.
    Useful after bulk-importing transactions or manually refreshing.
    """
    uid = int(get_jwt_identity())
    deleted = invalidate_user_caches(uid)
    logger.info("Cache bust user=%s deleted=%d keys", uid, deleted)
    return jsonify({
        "message": "Cache cleared.",
        "keys_deleted": deleted,
    })
