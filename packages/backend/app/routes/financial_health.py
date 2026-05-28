"""Financial Health Score API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.financial_health import FinancialHealthService

bp = Blueprint("financial_health", __name__)


@bp.post("/calculate")
@jwt_required()
def calculate():
    """Calculate financial health score."""
    data = request.get_json() or {}
    service = FinancialHealthService()
    result = service.calculate(
        monthly_income=float(data.get("monthly_income", 0)),
        monthly_expenses=data.get("expenses", []),
        savings_balance=float(data.get("savings_balance", 0)),
        debt_balance=float(data.get("debt_balance", 0)),
        monthly_debt_payment=float(data.get("monthly_debt_payment", 0)),
        investment_balance=float(data.get("investment_balance", 0)),
        goals=data.get("goals", []),
    )
    return jsonify(result)
