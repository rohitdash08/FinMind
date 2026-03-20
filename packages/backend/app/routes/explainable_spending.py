from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.explainable_spending import get_spending_insights

bp = Blueprint("explainable_spending", __name__)


@bp.route("/spending-insights", methods=["GET"])
@jwt_required()
def spending_insights():
    """
    GET /insights/spending-insights?month=2026-02

    Returns explainable insights about why spending changed vs the previous month.
    Each insight explains WHAT changed and WHY, with a confidence score.
    """
    user_id = get_jwt_identity()
    month = request.args.get("month")

    result = get_spending_insights(user_id=int(user_id), month=month)

    return jsonify(
        {
            "period_current": result.period_current,
            "period_previous": result.period_previous,
            "total_current": result.total_current,
            "total_previous": result.total_previous,
            "total_change_pct": result.total_change_pct,
            "summary": result.summary,
            "confidence": result.confidence,
            "insights": [
                {
                    "category": i.category,
                    "current_amount": i.current_amount,
                    "previous_amount": i.previous_amount,
                    "change_amount": i.change_amount,
                    "change_pct": i.change_pct,
                    "explanation": i.explanation,
                    "confidence": i.confidence,
                }
                for i in result.insights
            ],
        }
    )