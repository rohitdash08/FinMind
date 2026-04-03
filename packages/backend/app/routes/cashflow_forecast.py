from flask import Blueprint, request, jsonify, g
from ..services.cashflow_forecast import CashFlowForecastEngine
from ..middleware.auth import require_auth

cashflow_bp = Blueprint("cashflow", __name__)
engine = CashFlowForecastEngine()

@cashflow_bp.route("/api/analytics/cashflow/forecast", methods=["GET"])
@require_auth
def get_forecast():
    """Get cash flow forecast for the next N months."""
    user_id = g.user_id
    months = int(request.args.get("months_ahead", 3))
    balance = float(request.args.get("current_balance", 0))
    result = engine.forecast(user_id, months_ahead=min(months, 12), current_balance=balance)
    return jsonify(result)

@cashflow_bp.route("/api/analytics/cashflow/income", methods=["POST"])
@require_auth
def record_income():
    """Record an income entry for forecasting."""
    user_id = g.user_id
    data = request.get_json() or {}
    amount = data.get("amount")
    date_str = data.get("date")
    source = data.get("source", "salary")
    if not amount or not date_str:
        return jsonify({"error": "amount and date required"}), 400
    entry = engine.add_income(user_id, float(amount), date_str, source)
    return jsonify(entry), 201