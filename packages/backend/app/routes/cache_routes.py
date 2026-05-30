import logging

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.cache import get_stats, clear_stats, warm_user_cache

bp = Blueprint("cache", __name__)
logger = logging.getLogger("finmind.cache")


@bp.get("/stats")
@jwt_required()
def cache_stats():
    return jsonify(get_stats())


@bp.post("/stats/clear")
@jwt_required()
def reset_stats():
    clear_stats()
    return jsonify(message="stats cleared"), 200


@bp.post("/warm")
@jwt_required()
def warm_cache():
    uid = int(get_jwt_identity())
    warm_user_cache(uid)
    return jsonify(message="cache warmed"), 200
