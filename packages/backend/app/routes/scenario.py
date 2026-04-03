from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.scenario import simulate_scenario, compare_scenarios

scenario_bp = Blueprint("scenario", __name__, url_prefix="/scenario")


@scenario_bp.route("/simulate", methods=["POST"])
@jwt_required()
def simulate():
    """
    POST /scenario/simulate
    Body: {
      scenario: {type, ...params},
      horizon_months: int (optional, default 12)
    }
    Returns a full month-by-month projection.
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    scenario = body.get("scenario")
    if not scenario or not isinstance(scenario, dict):
        return jsonify({"error": "scenario object required"}), 400
    if "type" not in scenario:
        return jsonify({"error": "scenario.type required (expense_reduction, income_change, rent_change, savings_goal, debt_payoff)"}), 400
    horizon = int(body.get("horizon_months", 12))
    if not (1 <= horizon <= 120):
        return jsonify({"error": "horizon_months must be between 1 and 120"}), 400
    try:
        result = simulate_scenario(uid, scenario, horizon)
        return jsonify(result.to_dict()), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@scenario_bp.route("/compare", methods=["POST"])
@jwt_required()
def compare():
    """
    POST /scenario/compare
    Body: {
      scenarios: [{type, ...}, ...],
      horizon_months: int (optional)
    }
    Returns list of scenarios sorted by best projected net.
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    scenarios = body.get("scenarios")
    if not scenarios or not isinstance(scenarios, list) or len(scenarios) < 2:
        return jsonify({"error": "scenarios must be a list with at least 2 items"}), 400
    if len(scenarios) > 10:
        return jsonify({"error": "maximum 10 scenarios per comparison"}), 400
    horizon = int(body.get("horizon_months", 12))
    try:
        results = compare_scenarios(uid, scenarios, horizon)
        return jsonify({"count": len(results), "scenarios": results}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
