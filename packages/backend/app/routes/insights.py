from datetime import date
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


@bp.get("/weekly-summary")
@jwt_required()
def weekly_summary():
    uid = int(get_jwt_identity())
    # year_week format: YYYY-Www (e.g., 2023-W01)
    # Default to current week
    today = date.today()
    default_year_week = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
    year_week = (request.args.get("week") or default_year_week).strip()

    # Basic validation of year_week format
    try:
        year_str, week_str_prefix = year_week.split('-')
        if not week_str_prefix.startswith('W'):
            raise ValueError("Week string must start with 'W'")
        week_num_str = week_str_prefix[1:] # remove 'W'
        
        year_int = int(year_str)
        week_int = int(week_num_str)
        
        if not (1 <= week_int <= 53) or not (2000 <= year_int <= 2100): # Reasonable range for week and year
            raise ValueError("Invalid week number or year value")
        
        # Further checks could involve determining if a specific year has 53 weeks,
        # but for an initial implementation, this format check is sufficient.
    except (ValueError, IndexError):
        logger.warning(
            "Invalid 'week' parameter format: '%s'. Falling back to default current week.",
            year_week
        )
        year_week = default_year_week # Fallback to default if malformed

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    summary = weekly_financial_summary(
        uid,
        year_week,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Weekly financial summary served user=%s week=%s", uid, year_week)
    return jsonify(summary)
