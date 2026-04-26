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


@bp.get("/reminder-timing")
@jwt_required()
def reminder_timing():
    """Return optimal reminder timing recommendation (closes #111)."""
    from ..services.reminder_timing import optimal_reminder_timing, suggest_reminder_send_at

    uid = int(get_jwt_identity())
    due_date = (request.args.get("due_date") or "").strip()

    if due_date:
        result = suggest_reminder_send_at(uid, due_date)
    else:
        result = optimal_reminder_timing(uid)

    logger.info("Reminder timing served user=%s confidence=%s", uid, result["confidence"])
    return jsonify(result)
