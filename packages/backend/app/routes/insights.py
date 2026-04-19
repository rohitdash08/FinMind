from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion, weekly_financial_summary
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
    week_start = request.args.get("week_start")
    week_end = request.args.get("week_end")
    
    if not week_start or not week_end:
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        week_start = start_of_week.isoformat()
        week_end = end_of_week.isoformat()

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    
    summary = weekly_financial_summary(
        uid,
        week_start=week_start,
        week_end=week_end,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Weekly digest served user=%s week_start=%s week_end=%s", uid, week_start, week_end)
    return jsonify(summary)

