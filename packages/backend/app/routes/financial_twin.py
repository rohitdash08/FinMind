"""Financial Digital Twin API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.financial_twin import FinancialTwin

bp = Blueprint("financial_twin", __name__)


@bp.post("/simulate")
@jwt_required()
def simulate():
    """Run digital twin simulation."""
    data = request.get_json() or {}

    twin = FinancialTwin(
        monthly_income=float(data.get("monthly_income", 0)),
        monthly_expenses=data.get("expenses", []),
        current_savings=float(data.get("current_savings", 0)),
        debts=data.get("debts", []),
    )

    months = int(data.get("months", 12))
    scenarios = data.get("scenarios", {})

    projection = twin.simulate_months(months, scenarios)
    health = twin.health_score()
    recommendations = twin.recommend()

    return jsonify({
        "health": health,
        "projection": projection,
        "recommendations": recommendations,
    })


@bp.post("/what-if")
@jwt_required()
def what_if():
    """Run what-if scenario analysis."""
    data = request.get_json() or {}

    twin = FinancialTwin(
        monthly_income=float(data.get("monthly_income", 0)),
        monthly_expenses=data.get("expenses", []),
        current_savings=float(data.get("current_savings", 0)),
        debts=data.get("debts", []),
    )

    scenario = data.get("scenario", "custom")
    params = data.get("params", {})
    result = twin.what_if(scenario, params)

    return jsonify(result)


@bp.post("/recommendations")
@jwt_required()
def recommendations():
    """Get personalized financial recommendations."""
    data = request.get_json() or {}

    twin = FinancialTwin(
        monthly_income=float(data.get("monthly_income", 0)),
        monthly_expenses=data.get("expenses", []),
        current_savings=float(data.get("current_savings", 0)),
        debts=data.get("debts", []),
    )

    return jsonify({"recommendations": twin.recommend()})
