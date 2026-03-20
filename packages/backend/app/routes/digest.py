"""Weekly digest API routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import build_weekly_digest, current_week_string
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _digest_cache_key(uid: int, week: str) -> str:
    return f"user:{uid}:weekly_digest:{week}"


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Get the weekly financial digest/summary.

    Query params:
        week (str): ISO week in 'YYYY-Www' format (e.g. '2026-W12').
                     Defaults to current week.

    Headers:
        X-Gemini-Api-Key (str): Optional user-supplied Gemini API key.
        X-Insight-Persona (str): Optional persona override.

    Returns:
        JSON with complete weekly digest including summary, trends,
        category breakdown, daily spending, transactions, bills,
        and AI/heuristic insights.
    """
    uid = int(get_jwt_identity())
    week = (request.args.get("week") or current_week_string()).strip()
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    # Only cache when not using user-supplied keys (those may produce
    # different results)
    use_cache = not user_gemini_key
    if use_cache:
        key = _digest_cache_key(uid, week)
        cached = cache_get(key)
        if cached:
            logger.info("Weekly digest cache hit user=%s week=%s", uid, week)
            return jsonify(cached)

    try:
        payload = build_weekly_digest(
            uid,
            week_str=week,
            gemini_api_key=user_gemini_key,
            persona=persona,
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    if use_cache:
        cache_set(_digest_cache_key(uid, week), payload, ttl_seconds=600)

    logger.info("Weekly digest served user=%s week=%s method=%s", uid, week, payload.get("method"))
    return jsonify(payload)
