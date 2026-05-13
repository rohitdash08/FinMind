from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digests import weekly_financial_digest
from ..services.ai import monthly_budget_suggestion
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
    week_start_arg = (request.args.get("week_start") or "").strip()
    if week_start_arg:
        try:
            week_start = date.fromisoformat(week_start_arg)
        except ValueError:
            return jsonify(error="invalid week_start, expected YYYY-MM-DD"), 400
    else:
        week_start = None
    digest = weekly_financial_digest(uid, week_start)
    logger.info(
        "Weekly digest served user=%s week_start=%s",
        uid,
        digest["period"]["week_start"],
    )
    return jsonify(digest)
