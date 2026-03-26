"""Weekly financial digest endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import weekly_digest
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")

DIGEST_CACHE_TTL = 600  # 10 minutes


def _digest_cache_key(user_id: int, week: str, currency: str | None) -> str:
    suffix = f":{currency}" if currency else ""
    return f"user:{user_id}:digest:{week}{suffix}"


@bp.get("/weekly")
@jwt_required()
def get_weekly_digest():
    """Return a weekly financial summary digest.

    Query params
    ------------
    week : str, optional
        ISO week in ``YYYY-Wnn`` format.  Defaults to the current week.
    currency : str, optional
        Filter by currency code (e.g. ``USD``, ``EUR``, ``INR``).
    """
    uid = int(get_jwt_identity())
    week_param = (request.args.get("week") or "").strip() or None
    currency = (request.args.get("currency") or "").strip().upper() or None

    # Validate week format early
    if week_param:
        parts = week_param.split("-W")
        if len(parts) != 2:
            return jsonify(error="invalid week format, expected YYYY-Wnn"), 400
        try:
            year = int(parts[0])
            week = int(parts[1])
            if week < 1 or week > 53:
                raise ValueError
        except (ValueError, IndexError):
            return jsonify(error="invalid week format, expected YYYY-Wnn"), 400

    # Try cache
    cache_week = week_param or "_current"
    key = _digest_cache_key(uid, cache_week, currency)
    cached = cache_get(key)
    if cached:
        logger.info("Digest cache hit user=%s week=%s", uid, cache_week)
        return jsonify(cached)

    try:
        payload = weekly_digest(uid, week_str=week_param, currency=currency)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    cache_set(key, payload, ttl_seconds=DIGEST_CACHE_TTL)
    return jsonify(payload)
