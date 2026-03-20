from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.lifestyle_inflation import get_lifestyle_inflation

bp = Blueprint("lifestyle_inflation", __name__)


@bp.route("/lifestyle-inflation", methods=["GET"])
@jwt_required()
def lifestyle_inflation():
    """
    GET /insights/lifestyle-inflation?months=6&threshold=5

    Detects rising lifestyle expenses by comparing the older half of the period
    to the recent half. Returns inflation signals per category with severity.
    """
    user_id = get_jwt_identity()
    try:
        months = int(request.args.get("months", 6))
    except (ValueError, TypeError):
        months = 6
    try:
        threshold = float(request.args.get("threshold", 5.0))
    except (ValueError, TypeError):
        threshold = 5.0

    result = get_lifestyle_inflation(
        user_id=int(user_id), months=months, threshold_pct=threshold
    )

    return jsonify(
        {
            "analysis_months": result.analysis_months,
            "total_lifestyle_old": result.total_lifestyle_old,
            "total_lifestyle_new": result.total_lifestyle_new,
            "lifestyle_inflation_pct": result.lifestyle_inflation_pct,
            "top_inflated_category": result.top_inflated_category,
            "is_inflating": result.is_inflating,
            "summary": result.summary,
            "inflation_signals": [
                {
                    "category": s.category,
                    "is_lifestyle": s.is_lifestyle,
                    "monthly_avg_old": s.monthly_avg_old,
                    "monthly_avg_new": s.monthly_avg_new,
                    "inflation_pct": s.inflation_pct,
                    "severity": s.severity,
                    "trend_note": s.trend_note,
                }
                for s in result.inflation_signals
            ],
        }
    )