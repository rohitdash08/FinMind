import logging
import re
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.ai import weekly_digest
from ..services.cache import cache_get, cache_set

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")

_ISO_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def _current_iso_week() -> str:
    today = date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


@bp.get("/weekly")
@jwt_required()
def weekly():
    uid = int(get_jwt_identity())
    raw = (request.args.get("week") or _current_iso_week()).strip()
    m = _ISO_WEEK_RE.match(raw)
    if not m:
        return jsonify({"error": "Invalid week format. Expected YYYY-Wnn."}), 400
    year, week_num = int(m.group(1)), int(m.group(2))
    if week_num < 1 or week_num > 53:
        return jsonify({"error": "Week number must be between 01 and 53."}), 400

    cache_key = f"user:{uid}:digest_weekly:{year}-W{week_num:02d}"
    cached = cache_get(cache_key)
    if cached:
        logger.info("Weekly digest cache hit user=%s week=%s-W%02d", uid, year, week_num)
        return jsonify(cached)

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    result = weekly_digest(
        uid,
        year,
        week_num,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )

    cache_set(cache_key, result, ttl_seconds=3600)
    logger.info("Weekly digest served user=%s week=%s-W%02d", uid, year, week_num)
    return jsonify(result)
