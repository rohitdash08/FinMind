from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion, weekly_digest as weekly_digest_service, _week_range
from ..services.cache import cache_get, cache_set, weekly_digest_key
import logging

bp = Blueprint("insights", __name__)
logger = logging.getLogger("finmind.insights")


@bp.get("/budget-suggestion")
@jwt_required()
def budget_suggestion():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    suggestion = monthly_budget_suggestion(
        uid,
        ym,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Budget suggestion served user=%s month=%s", uid, ym)
    return jsonify(suggestion)


@bp.get("/weekly-digest")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    today = date.today()
    default_week = (today - timedelta(days=today.weekday())).isoformat()
    week_param = (request.args.get("week") or default_week).strip()

    try:
        date.fromisoformat(week_param)
    except ValueError:
        return jsonify(error="invalid week, expected YYYY-MM-DD"), 400

    # Normalize any day-of-week to that week's Monday so cache keys are consistent.
    week_start_normalized = _week_range(week_param)[0].isoformat()

    key = weekly_digest_key(uid, week_start_normalized)
    cached = cache_get(key)
    if cached:
        return jsonify(cached)

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    digest = weekly_digest_service(
        uid,
        week_start_normalized,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    cache_set(key, digest, ttl_seconds=900)
    logger.info(
        "Weekly digest served user=%s week=%s method=%s",
        uid,
        week_start_normalized,
        digest.get("method"),
    )
    return jsonify(digest)
