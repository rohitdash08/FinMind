import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.cashflow import forecast_cash_flow

bp = Blueprint("cashflow", __name__)
logger = logging.getLogger("finmind.cashflow_routes")


@bp.get("/forecast")
@jwt_required()
def get_forecast():
    """
    Get cash flow forecast for upcoming months.

    Query params:
        months (int, 1-12, default 3): Number of months to forecast

    Returns:
        {
            "months": [...],
            "summary": {
                "avg_monthly_surplus": float,
                "trend": "improving" | "declining" | "stable",
                "data_quality": "high" | "medium" | "low",
                "historical_months_used": int
            }
        }
    """
    uid = int(get_jwt_identity())
    try:
        months = int(request.args.get("months", 3))
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 12"), 400

    if not (1 <= months <= 12):
        return jsonify(error="months must be between 1 and 12"), 400

    result = forecast_cash_flow(uid, months)
    logger.info("Cash flow forecast uid=%s months=%s", uid, months)
    return jsonify(result)

