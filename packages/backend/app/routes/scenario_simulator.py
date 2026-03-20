from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.scenario_simulator import run_scenario, ALLOWED_SCENARIO_TYPES

bp = Blueprint("scenario_simulator", __name__)


@bp.route("/scenario-simulator", methods=["POST"])
@jwt_required()
def scenario_simulator():
    """
    POST /insights/scenario-simulator

    Simulate a financial decision and compare it to the current baseline.

    Request body (JSON):
        scenario_type: str  — one of: reduce_category, increase_income,
                               increase_expense, change_rent, salary_change
        value: float        — magnitude of the change (see service docs)
        category: str       — (optional) category name, required for reduce_category
        months: int         — (optional) forecast horizon in months (1-24, default 6)
        scenario_name: str  — (optional) human-friendly scenario label
    """
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    scenario_type = data.get("scenario_type", "increase_expense")
    value = float(data.get("value", 0))
    category = data.get("category")
    months = int(data.get("months", 6))
    scenario_name = data.get("scenario_name")

    if scenario_type not in ALLOWED_SCENARIO_TYPES:
        return jsonify(
            {
                "error": f"Invalid scenario_type. Must be one of: {', '.join(ALLOWED_SCENARIO_TYPES)}"
            }
        ), 400

    result = run_scenario(
        user_id=int(user_id),
        scenario_type=scenario_type,
        value=value,
        category=category,
        months=months,
        scenario_name=scenario_name,
    )

    def _serialize_monthly(monthly):
        return [
            {
                "month": r.month,
                "income": r.income,
                "expenses": r.expenses,
                "net": r.net,
                "cumulative_net": r.cumulative_net,
            }
            for r in monthly
        ]

    def _serialize_scenario(s):
        return {
            "scenario_name": s.scenario_name,
            "description": s.description,
            "monthly_results": _serialize_monthly(s.monthly_results),
            "total_net_change": s.total_net_change,
            "break_even_month": s.break_even_month,
            "recommendation": s.recommendation,
        }

    return jsonify(
        {
            "baseline": _serialize_scenario(result.baseline),
            "scenario": _serialize_scenario(result.scenario),
            "net_impact_monthly": result.net_impact_monthly,
            "net_impact_total": result.net_impact_total,
            "verdict": result.verdict,
            "allowed_scenario_types": list(ALLOWED_SCENARIO_TYPES),
        }
    )