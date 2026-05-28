"""Dynamic Budget Suggestion API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.dynamic_budget import DynamicBudgetService

bp = Blueprint("dynamic_budget", __name__)


@bp.post("/suggest")
@jwt_required()
def suggest():
    """Generate budget suggestions."""
    data = request.get_json() or {}
    service = DynamicBudgetService()

    result = service.generate_suggestions(
        transactions=data.get("transactions", []),
        monthly_income=float(data.get("monthly_income", 0)),
        savings_goal=float(data.get("savings_goal", 0)),
        aggressive=bool(data.get("aggressive", False)),
    )

    return jsonify(result)


@bp.post("/allocation")
@jwt_required()
def allocation():
    """Get recommended budget allocation."""
    data = request.get_json() or {}
    service = DynamicBudgetService()
    result = service.generate_suggestions(
        transactions=data.get("transactions", []),
        monthly_income=float(data.get("monthly_income", 0)),
    )
    return jsonify({"allocation": result["budget_allocation"]})
