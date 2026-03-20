from datetime import date
from flask import Blueprint, jsonify, request, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.memory_cache import memory_cache, ANALYTICS_TTL, _build_cache_key
import logging

bp = Blueprint("insights", __name__)
logger = logging.getLogger("finmind.insights")


@bp.get("/budget-suggestion")
@jwt_required()
def budget_suggestion():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    # Check in-memory cache (15 min TTL for analytics)
    mem_key = _build_cache_key("insights", uid)
    mem_cached = memory_cache.get(mem_key)
    if mem_cached is not None:
        g.cache_hit = True
        return mem_cached

    g.cache_hit = False
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    suggestion = monthly_budget_suggestion(
        uid,
        ym,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Budget suggestion served user=%s month=%s", uid, ym)
    resp = jsonify(suggestion)
    memory_cache.set(mem_key, resp, timeout=ANALYTICS_TTL)
    return jsonify(suggestion)
