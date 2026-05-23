from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.weekly_digest import build_weekly_digest
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
    end_raw = (request.args.get("end_date") or "").strip()
    try:
        end_date = date.fromisoformat(end_raw) if end_raw else None
    except ValueError:
        return jsonify(error="invalid end_date, expected YYYY-MM-DD"), 400

    digest = build_weekly_digest(uid, end_date=end_date)
    logger.info(
        "Weekly digest served user=%s start=%s end=%s",
        uid,
        digest["period"]["start_date"],
        digest["period"]["end_date"],
    )
    return jsonify(digest)
