"""Weekly financial digest endpoint."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import weekly_digest
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _digest_cache_key(uid: int, ref: str) -> str:
    return f"digest:weekly:{uid}:{ref}"


@bp.get("/weekly")
@jwt_required()
def get_weekly_digest():
    """Return the weekly financial summary for the authenticated user.

    Query params:
        date: reference date (YYYY-MM-DD). Defaults to today.
              The digest covers the previous full Mon-Sun week.
    """
    uid = int(get_jwt_identity())
    raw_date = (request.args.get("date") or "").strip()

    ref_date = None
    if raw_date:
        try:
            ref_date = date.fromisoformat(raw_date)
        except ValueError:
            return jsonify(error="invalid date, expected YYYY-MM-DD"), 400

    ref_key = (ref_date or date.today()).isoformat()
    cache_key = _digest_cache_key(uid, ref_key)
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    payload = weekly_digest(uid, ref_date)
    cache_set(cache_key, payload, ttl_seconds=600)
    logger.info("Weekly digest served user=%s ref=%s", uid, ref_key)
    return jsonify(payload)
