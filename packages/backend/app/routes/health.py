"""Financial Health Score API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.health_score import calculate_health_score

bp = Blueprint("health", __name__)


@bp.post("/score")
@jwt_required()
def get_score():
    """Calculate financial health score.

    Expects JSON body with:
    - income: monthly income (float)
    - expenses: list of current period transactions
    - previous_expenses: list of previous period transactions (optional)
    - bills: list of bills with status field (optional)
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    report = calculate_health_score(
        income=float(data.get("income", 0)),
        expenses=data.get("expenses", []),
        previous_expenses=data.get("previous_expenses", []),
        bills=data.get("bills", []),
    )

    return jsonify(report.to_dict())
