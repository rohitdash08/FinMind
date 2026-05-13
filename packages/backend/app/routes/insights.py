from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.weekly_digest import weekly_financial_digest
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
    raw_week = (
        request.args.get("week_start") or request.args.get("date") or ""
    ).strip()
    currency = (request.args.get("currency") or "").strip().upper() or None
    reference_date = None
    if raw_week:
        try:
            reference_date = date.fromisoformat(raw_week)
        except ValueError:
            return jsonify(error="invalid week_start"), 400
    payload = weekly_financial_digest(uid, reference_date, currency)
    logger.info(
        "Weekly summary served user=%s week_start=%s currency=%s",
        uid,
        payload["period"]["week_start"],
        currency or "all",
    )
    return jsonify(payload)
