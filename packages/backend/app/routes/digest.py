from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import generate_weekly_digest
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    week_start_raw = request.args.get("week_start")
    week_start = None
    if week_start_raw:
        try:
            week_start = date.fromisoformat(week_start_raw)
            if week_start.weekday() != 0:
                week_start = week_start - timedelta(days=week_start.weekday())
        except ValueError:
            return jsonify(error="invalid week_start, expected YYYY-MM-DD"), 400

    cache_key = f"digest:{uid}:weekly:{week_start.isoformat() if week_start else 'current'}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        digest = generate_weekly_digest(uid, week_start)
    except Exception:
        logger.exception("Weekly digest generation failed user=%s", uid)
        return jsonify(error="failed to generate digest"), 500

    cache_set(cache_key, digest, ttl_seconds=600)
    logger.info("Weekly digest generated user=%s", uid)
    return jsonify(digest)
