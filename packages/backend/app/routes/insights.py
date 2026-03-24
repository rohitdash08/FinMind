from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
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


from datetime import date
from ..services.digest import weekly_digest as _weekly_digest


@bp.get("/weekly-digest")
@jwt_required()
def weekly_digest():
    """Return a weekly financial digest.

    Query params:
        week (optional): ISO date (YYYY-MM-DD) of any day in the desired week.
                         Defaults to the current week.
    """
    uid = int(get_jwt_identity())
    week_param = request.args.get("week")
    week_start = None
    if week_param:
        try:
            week_start = date.fromisoformat(week_param)
        except ValueError:
            return jsonify({"error": "Invalid week format. Use YYYY-MM-DD."}), 400

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    result = _weekly_digest(
        uid,
        week_start=week_start,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Weekly digest served user=%s week_start=%s", uid, result.get("week_start"))
    return jsonify(result)
