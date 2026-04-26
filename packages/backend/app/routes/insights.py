from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.subscriptions import (
    detect_subscriptions,
    detect_subscription_cost_increases,
    find_duplicate_transactions,
    detect_lifestyle_inflation,
)
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


@bp.get("/subscriptions")
@jwt_required()
def subscriptions():
    """Detect likely subscription services from recurring charges (closes #109)."""
    uid = int(get_jwt_identity())
    result = detect_subscriptions(uid)
    logger.info(
        "Subscription detection served user=%s found=%s",
        uid,
        result["total_subscriptions_found"],
    )
    return jsonify(result)


@bp.get("/subscription-cost-increases")
@jwt_required()
def subscription_cost_increases():
    """Detect subscription price increases (closes #110)."""
    uid = int(get_jwt_identity())
    result = detect_subscription_cost_increases(uid)
    logger.info(
        "Subscription cost-increase check served user=%s found=%s",
        uid,
        result["total_increases_found"],
    )
    return jsonify(result)


@bp.get("/duplicate-transactions")
@jwt_required()
def duplicate_transactions():
    """Find likely duplicate expense entries (closes #113)."""
    uid = int(get_jwt_identity())
    result = find_duplicate_transactions(uid)
    logger.info(
        "Duplicate transaction check served user=%s found=%s",
        uid,
        result["total_duplicates_found"],
    )
    return jsonify(result)


@bp.get("/lifestyle-inflation")
@jwt_required()
def lifestyle_inflation():
    """Detect rising lifestyle expenses over time (closes #118)."""
    uid = int(get_jwt_identity())
    result = detect_lifestyle_inflation(uid)
    logger.info(
        "Lifestyle inflation check served user=%s pct=%.1f",
        uid,
        result["overall_change_pct"],
    )
    return jsonify(result)
