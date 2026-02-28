from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import weekly_digest
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")

DIGEST_TTL = 900  # 15 minutes


@bp.get("/weekly")
@jwt_required()
def get_weekly_digest():
    """Return a weekly financial summary for the authenticated user.

    Query params:
        year  – ISO year  (default: current)
        week  – ISO week  (default: current)
    """
    uid = int(get_jwt_identity())
    year = request.args.get("year", type=int)
    week = request.args.get("week", type=int)

    if (year is None) != (week is None):
        return jsonify({"error": "Provide both year and week, or neither."}), 400

    cache_key = f"user:{uid}:weekly_digest:{year or 'cur'}-{week or 'cur'}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    digest = weekly_digest(uid, iso_year=year, iso_week=week)
    cache_set(cache_key, digest, ttl_seconds=DIGEST_TTL)
    logger.info("Weekly digest served user=%s week=%s", uid, digest["week"])
    return jsonify(digest)
