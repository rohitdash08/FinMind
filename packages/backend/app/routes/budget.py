import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.budget import optimize_budget

bp = Blueprint("budget", __name__)
logger = logging.getLogger("finmind.budget_routes")


@bp.get("/optimize")
@jwt_required()
def optimize():
    """
    Get autonomous budget optimization recommendations.

    Query params:
        target_savings_pct (float, 5-50, default 20): Target savings % of income
        months (int, 1-12, default 3): Historical months to analyze

    Returns:
        {
            current_state: avg income/expenses/savings/savings%
            target_state: target savings and gap
            recommendations: [{type, priority, category, current, suggested, saving}]
            estimated_monthly_savings: float
            projected_savings_pct: float
            category_breakdown: top 10 categories by spending
        }
    """
    uid = int(get_jwt_identity())

    try:
        target_pct = float(request.args.get("target_savings_pct", 20.0))
        months = int(request.args.get("months", 3))
    except (ValueError, TypeError):
        return jsonify(error="Invalid query parameters"), 400

    if not (5 <= target_pct <= 50):
        return jsonify(error="target_savings_pct must be between 5 and 50"), 400
    if not (1 <= months <= 12):
        return jsonify(error="months must be between 1 and 12"), 400

    result = optimize_budget(uid, target_pct, months)
    logger.info("Budget optimize uid=%s target_pct=%s", uid, target_pct)
    return jsonify(result)
