from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import weekly_summary
from ..services.cache import cache_get, cache_set

bp = Blueprint("digest", __name__)


def _weekly_digest_key(user_id: int, week_start: str) -> str:
    return f"user:{user_id}:weekly_digest:{week_start}"


@bp.get("/weekly")
@jwt_required()
def get_weekly_digest():
    """Return a weekly financial digest.

    Query params:
        week: ISO date string (YYYY-MM-DD) for the Monday of the desired week.
              Defaults to the current week's Monday.
    """
    uid = int(get_jwt_identity())
    week_param = request.args.get("week", "").strip()

    if week_param:
        try:
            week_start = date.fromisoformat(week_param)
        except ValueError:
            return jsonify(error="Invalid date format. Use YYYY-MM-DD."), 400
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)

    cache_key = _weekly_digest_key(uid, week_start.isoformat())
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    payload = weekly_summary(uid, week_start, week_end)

    cache_set(cache_key, payload, ttl_seconds=3600)
    return jsonify(payload)
