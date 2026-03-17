from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion, MIN_MONTHS, MAX_MONTHS
from ..services.cache import cache_get, cache_set, budget_suggestion_key
import logging

bp = Blueprint("insights", __name__)
logger = logging.getLogger("finmind.insights")

BUDGET_CACHE_TTL = 1800  # 30 minutes


@bp.get("/budget-suggestion")
@jwt_required()
def budget_suggestion():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    try:
        lookback = int(request.args.get("months", str(MAX_MONTHS)))
        lookback = max(MIN_MONTHS, min(MAX_MONTHS, lookback))
    except (ValueError, TypeError):
        lookback = MAX_MONTHS

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    cache_key = budget_suggestion_key(uid, ym, lookback)
    cached = cache_get(cache_key)
    if cached and not user_gemini_key:
        logger.info("Budget suggestion cache hit user=%s month=%s", uid, ym)
        return jsonify(cached)

    suggestion = monthly_budget_suggestion(
        uid,
        ym,
        lookback=lookback,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )

    if not user_gemini_key:
        cache_set(cache_key, suggestion, ttl_seconds=BUDGET_CACHE_TTL)

    logger.info(
        "Budget suggestion served user=%s month=%s lookback=%s method=%s",
        uid,
        ym,
        lookback,
        suggestion.get("method"),
    )
    return jsonify(suggestion)


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    year, month = ym.split("-")
    if not (year.isdigit() and month.isdigit()):
        return False
    m = int(month)
    return 1 <= m <= 12
