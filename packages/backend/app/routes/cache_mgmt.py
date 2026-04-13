from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import redis_client
import logging

bp = Blueprint("cache_mgmt", __name__)
logger = logging.getLogger("finmind.cache_mgmt")

_USER_CACHE_PREFIX = "user_cache"


def _user_prefix(uid: int) -> str:
    return f"{_USER_CACHE_PREFIX}:{uid}:"


@bp.get("/stats")
@jwt_required()
def cache_stats():
    """Return cache hit/miss statistics for the current user."""
    uid = int(get_jwt_identity())
    prefix = _user_prefix(uid)

    try:
        keys = redis_client.keys(f"{prefix}*")
    except Exception:
        keys = []

    total_keys = len(keys)
    # Track hits/misses via a counter key
    hit_key = f"{prefix}__hits"
    miss_key = f"{prefix}__misses"

    try:
        hits = int(redis_client.get(hit_key) or 0)
        misses = int(redis_client.get(miss_key) or 0)
    except Exception:
        hits = 0
        misses = 0

    total_lookups = hits + misses
    hit_rate = round((hits / total_lookups) * 100, 2) if total_lookups > 0 else 0.0

    logger.info("Cache stats user=%s keys=%s hits=%s misses=%s", uid, total_keys, hits, misses)
    return jsonify(
        total_keys=total_keys,
        hits=hits,
        misses=misses,
        hit_rate=hit_rate,
    )


@bp.post("/invalidate")
@jwt_required()
def invalidate_cache():
    """Clear cache for specific keys or all keys for the current user."""
    uid = int(get_jwt_identity())
    prefix = _user_prefix(uid)
    data = request.get_json(silent=True) or {}
    specific_keys = data.get("keys")

    deleted = 0
    try:
        if specific_keys and isinstance(specific_keys, list):
            for k in specific_keys:
                full_key = f"{prefix}{k}"
                deleted += redis_client.delete(full_key)
        else:
            # Clear all user cache keys
            all_keys = redis_client.keys(f"{prefix}*")
            if all_keys:
                deleted = redis_client.delete(*all_keys)
    except Exception:
        pass

    logger.info("Cache invalidated user=%s deleted=%s", uid, deleted)
    return jsonify(deleted=deleted)


@bp.get("/keys")
@jwt_required()
def list_keys():
    """List cached keys for the current user."""
    uid = int(get_jwt_identity())
    prefix = _user_prefix(uid)

    try:
        raw_keys = redis_client.keys(f"{prefix}*")
        keys = [k.replace(prefix, "") if isinstance(k, str) else k.decode().replace(prefix, "") for k in raw_keys]
    except Exception:
        keys = []

    logger.info("Cache keys listed user=%s count=%s", uid, len(keys))
    return jsonify(keys=keys)
