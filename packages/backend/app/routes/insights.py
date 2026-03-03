import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.ai import monthly_budget_suggestion, weekly_financial_summary

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
    raw_end_date = (request.args.get("end_date") or "").strip()
    if raw_end_date:
        try:
            end_date = date.fromisoformat(raw_end_date)
        except ValueError:
            return jsonify(error="invalid end_date, expected YYYY-MM-DD"), 400
    else:
        end_date = date.today()

    payload = weekly_financial_summary(uid, end_date=end_date)
    logger.info(
        "Weekly summary served user=%s start=%s end=%s",
        uid,
        payload["period"]["start_date"],
        payload["period"]["end_date"],
    )
    return jsonify(payload)
