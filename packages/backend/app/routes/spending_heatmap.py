"""
Spending Trend Heatmap Route (#116)
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.spending_heatmap import get_spending_heatmap

bp = Blueprint("spending_heatmap", __name__)
logger = logging.getLogger("finmind.spending_heatmap")


@bp.get("/spending-heatmap")
@jwt_required()
def get_heatmap():
    """
    Get spending heatmap data for visualization.

    Query Parameters:
        months (int): Months to analyze (1-12, default: 6)
        view (str): 'daily', 'weekday', or 'monthly' (default: 'daily')

    Returns:
        Heatmap cells with dates, amounts, and intensity levels (0-4)
    """
    uid = int(get_jwt_identity())

    try:
        months = min(12, max(1, int(request.args.get("months", 6))))
    except (ValueError, TypeError):
        months = 6

    view = request.args.get("view", "daily")
    if view not in ("daily", "weekday", "monthly"):
        view = "daily"

    result = get_spending_heatmap(uid, months=months, view=view)
    logger.info("Heatmap served user=%s months=%s view=%s", uid, months, view)
    return jsonify(result)
