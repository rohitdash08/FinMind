"""Cash-flow Forecast API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.cashflow_forecast import CashFlowForecastService

bp = Blueprint("cashflow_forecast", __name__)


@bp.post("/forecast")
@jwt_required()
def forecast():
    """Generate cash-flow forecast."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}

    service = CashFlowForecastService()
    result = service.forecast(
        transactions=data.get("transactions", []),
        horizon_days=int(data.get("horizon_days", 30)),
        current_balance=float(data.get("current_balance", 0)),
    )

    return jsonify(result)


@bp.post("/recurring")
@jwt_required()
def detect_recurring():
    """Detect recurring transactions."""
    data = request.get_json() or {}
    service = CashFlowForecastService()
    recurring = service._detect_recurring(data.get("transactions", []))
    return jsonify({"recurring": recurring, "count": len(recurring)})


@bp.post("/trend")
@jwt_required()
def analyze_trend():
    """Analyze income/expense trends."""
    data = request.get_json() or {}
    service = CashFlowForecastService()
    daily = service._daily_totals(data.get("transactions", []))
    trend = service._calculate_trend(daily, int(data.get("days_back", 30)))
    return jsonify(trend)
