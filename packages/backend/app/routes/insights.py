from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion, weekly_digest_suggestion
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
    
    end_date_str = request.args.get("end_date")
    if end_date_str:
        end_date = date.fromisoformat(end_date_str)
    else:
        end_date = date.today()
        
    start_date_str = request.args.get("start_date")
    if start_date_str:
        start_date = date.fromisoformat(start_date_str)
    else:
        start_date = end_date - timedelta(days=6)
        
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    
    suggestion = weekly_digest_suggestion(
        uid,
        start_date,
        end_date,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Weekly digest served user=%s start=%s end=%s", uid, start_date, end_date)
    return jsonify(suggestion)
