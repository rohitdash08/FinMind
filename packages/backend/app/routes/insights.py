from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.weekly_digest import generate_weekly_digest
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
    """Generate a smart weekly financial digest.

    Query params:
        date: Reference date (YYYY-MM-DD, defaults to today). The digest covers
            the ISO week (Mon–Sun) that contains this date.
    """
    uid = int(get_jwt_identity())
    date_str = (request.args.get("date") or "").strip()
    reference_date = None
    if date_str:
        try:
            reference_date = date.fromisoformat(date_str)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    digest = generate_weekly_digest(uid, reference_date=reference_date)
    logger.info("Weekly digest served user=%s reference_date=%s", uid, reference_date)
    return jsonify(digest)
