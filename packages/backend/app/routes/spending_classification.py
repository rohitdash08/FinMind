"""
Essential vs Discretionary Spending Breakdown Route (#120)
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.spending_classification import get_spending_breakdown

bp = Blueprint("spending_classification", __name__)
logger = logging.getLogger("finmind.spending_classification")


@bp.get("/spending-breakdown")
@jwt_required()
def get_breakdown():
    """
    Get essential vs discretionary spending breakdown.

    Query Parameters:
        months (int): Number of months to analyze (1-12, default: 3)
        month (str): Specific month YYYY-MM (overrides months)

    Returns:
        JSON with essential/discretionary breakdown, percentages, categories, insights
    """
    uid = int(get_jwt_identity())
    month = request.args.get("month")

    try:
        months = min(12, max(1, int(request.args.get("months", 3))))
    except (ValueError, TypeError):
        months = 3

    result = get_spending_breakdown(uid, months=months, month=month)
    logger.info(
        "Spending breakdown served user=%s months=%s month=%s",
        uid, months, month,
    )
    return jsonify(result)
