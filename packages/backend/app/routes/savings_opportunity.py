"""
Savings Opportunity Detection Route (#119)
Provides endpoints to detect and retrieve savings opportunities for users.
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.savings_opportunity import detect_savings_opportunities

bp = Blueprint("savings_opportunity", __name__)
logger = logging.getLogger("finmind.savings_opportunity")


@bp.get("/savings-opportunities")
@jwt_required()
def get_savings_opportunities():
    """
    Detect savings opportunities for the authenticated user.

    Query Parameters:
        months (int): Number of months to analyze (1-12, default: 3)

    Returns:
        JSON with list of opportunities and total potential savings
    """
    uid = int(get_jwt_identity())
    try:
        months = min(12, max(1, int(request.args.get("months", 3))))
    except (ValueError, TypeError):
        months = 3

    result = detect_savings_opportunities(uid, months=months)
    logger.info(
        "Savings opportunities detected for user=%s months=%s opportunities=%d",
        uid,
        months,
        len(result.get("opportunities", [])),
    )
    return jsonify(result)


@bp.get("/savings-opportunities/summary")
@jwt_required()
def get_savings_summary():
    """
    Get a brief summary of savings opportunities.

    Returns:
        JSON with opportunity count and total potential savings
    """
    uid = int(get_jwt_identity())
    result = detect_savings_opportunities(uid, months=3)
    return jsonify({
        "opportunity_count": len(result.get("opportunities", [])),
        "total_potential_savings": result.get("total_potential_savings", 0),
        "summary": result.get("summary", ""),
        "monthly_spend_avg": result.get("monthly_spend_avg", 0),
    })
