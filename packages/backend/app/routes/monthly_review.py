"""
Guided Monthly Financial Review Route (#102)
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from datetime import date

from ..services.monthly_review import generate_monthly_review, REVIEW_STEPS

bp = Blueprint("monthly_review", __name__)
logger = logging.getLogger("finmind.monthly_review")


@bp.get("/monthly-review")
@jwt_required()
def get_monthly_review():
    """
    Get a guided monthly financial review.

    Query Parameters:
        month (str): Month in YYYY-MM format (defaults to last month)

    Returns:
        Structured review with 6 steps, insights, and action items
    """
    uid = int(get_jwt_identity())
    month = request.args.get("month")

    result = generate_monthly_review(uid, month=month)
    logger.info("Monthly review served user=%s month=%s", uid, result["month"])
    return jsonify(result)


@bp.get("/monthly-review/steps")
def get_review_steps():
    """
    Get the list of review steps (no auth needed - used for frontend setup).

    Returns:
        List of review steps with IDs, titles, and descriptions
    """
    return jsonify({"steps": REVIEW_STEPS, "total": len(REVIEW_STEPS)})
