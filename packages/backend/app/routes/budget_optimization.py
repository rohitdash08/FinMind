from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.budget_optimization import get_budget_optimization

bp = Blueprint("budget_optimization", __name__)


@bp.route("/budget-optimization", methods=["GET"])
@jwt_required()
def budget_optimization():
    """
    GET /insights/budget-optimization?months=3

    Returns autonomous budget optimization recommendations based on spending behavior.
    Detects overspending patterns, suggests reallocations, and adapts to trends.
    """
    user_id = get_jwt_identity()

    try:
        months = int(request.args.get("months", 3))
    except (ValueError, TypeError):
        months = 3

    result = get_budget_optimization(user_id=int(user_id), months=months)

    return jsonify(
        {
            "total_monthly_avg": result.total_monthly_avg,
            "total_suggested_budget": result.total_suggested_budget,
            "total_potential_savings": result.total_potential_savings,
            "months_analyzed": result.months_analyzed,
            "summary": result.summary,
            "recommendations": [
                {
                    "category": r.category,
                    "current_avg": r.current_avg,
                    "suggested_budget": r.suggested_budget,
                    "potential_saving": r.potential_saving,
                    "overspending": r.overspending,
                    "recommendation": r.recommendation,
                    "priority": r.priority,
                }
                for r in result.recommendations
            ],
            "reallocations": [
                {
                    "from_category": rl.from_category,
                    "to_category": rl.to_category,
                    "suggested_amount": rl.suggested_amount,
                    "reason": rl.reason,
                }
                for rl in result.reallocations
            ],
        }
    )