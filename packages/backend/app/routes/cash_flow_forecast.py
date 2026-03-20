from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.cash_flow_forecast import get_cash_flow_forecast

bp = Blueprint("cash_flow_forecast", __name__)


@bp.route("/cash-flow-forecast", methods=["GET"])
@jwt_required()
def cash_flow_forecast():
    """
    GET /insights/cash-flow-forecast?months=3

    Returns projected cash flow for the next N months (default 3, max 6).
    Includes irregular expense detection and confidence indicators.
    """
    user_id = get_jwt_identity()

    try:
        months = int(request.args.get("months", 3))
    except (ValueError, TypeError):
        months = 3

    result = get_cash_flow_forecast(user_id=int(user_id), forecast_months=months)

    return jsonify(
        {
            "current_balance_estimate": result.current_balance_estimate,
            "avg_monthly_income": result.avg_monthly_income,
            "avg_monthly_expenses": result.avg_monthly_expenses,
            "overall_confidence": result.overall_confidence,
            "trend": result.trend,
            "message": result.message,
            "monthly_projections": [
                {
                    "month": p.month,
                    "projected_income": p.projected_income,
                    "projected_expenses": p.projected_expenses,
                    "projected_net": p.projected_net,
                    "confidence": p.confidence,
                }
                for p in result.monthly_projections
            ],
            "irregular_expenses": [
                {
                    "category": ie.category,
                    "typical_month": ie.typical_month,
                    "estimated_amount": ie.estimated_amount,
                    "frequency_months": ie.frequency_months,
                }
                for ie in result.irregular_expenses
            ],
        }
    )