from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.cache import cache_get, cache_set
from ..services.savings import detect_savings_opportunities
from ..extensions import db
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


@bp.get("/savings")
@jwt_required()
def savings_opportunities():
    """
    Identify categories where the user can realistically save money.

    Query params:
      months (int, 1-12, default 3) — comparison window
    """
    uid = int(get_jwt_identity())
    try:
        months = int(request.args.get("months", 3))
        months = max(1, min(12, months))
    except (ValueError, TypeError):
        months = 3

    cache_key = f"user:{uid}:savings:{months}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    result = detect_savings_opportunities(uid, db.session, months=months)
    cache_set(cache_key, result, ttl_seconds=600)
    logger.info("Savings opportunities served user=%s months=%s", uid, months)
    return jsonify(result)
