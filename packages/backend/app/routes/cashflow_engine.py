from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.cashflow_engine import get_cashflow_forecast

bp = Blueprint("cashflow_engine", __name__)

@bp.route("/cashflow-forecast", methods=["GET"])
@jwt_required()
def cashflow_forecast():
    user_id = get_jwt_identity()
    try:
        horizon = int(request.args.get("horizon", 30))
        starting_balance = float(request.args.get("starting_balance", 0.0))
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid parameter: {e}"}), 400
    view = request.args.get("view", "all")
    result = get_cashflow_forecast(user_id, horizon, starting_balance)
    response = {
        "horizon_days": result.horizon_days,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "starting_balance": result.starting_balance,
        "projected_end_balance": result.projected_end_balance,
        "total_projected_income": result.total_projected_income,
        "total_projected_expenses": result.total_projected_expenses,
        "net_cash_flow": result.net_cash_flow,
        "key_dates": result.key_dates,
        "generated_at": result.generated_at,
    }
    if view in ("daily", "all"):
        response["daily_projections"] = [{"date": p.date, "income": p.income, "expenses": p.expenses, "net": p.net, "running_balance": p.running_balance, "sources": p.sources} for p in result.daily_projections]
    if view in ("weekly", "all"):
        response["weekly_summary"] = result.weekly_summary
    if view in ("monthly", "all"):
        response["monthly_summary"] = result.monthly_summary
    return jsonify(response)
