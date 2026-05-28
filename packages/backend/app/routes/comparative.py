"""Comparative spending analysis API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.comparative import compare_categories, compare_periods, compare_income_expenses

bp = Blueprint("comparative", __name__)


@bp.post("/categories")
@jwt_required()
def category_comparison():
    """Compare spending across categories."""
    data = request.get_json() or {}
    transactions = data.get("transactions", [])
    result = compare_categories(transactions)
    return jsonify(result)


@bp.post("/periods")
@jwt_required()
def period_comparison():
    """Compare spending between two time periods."""
    data = request.get_json() or {}
    current = data.get("current_transactions", [])
    previous = data.get("previous_transactions", [])
    current_label = data.get("current_label", "current period")
    previous_label = data.get("previous_label", "previous period")

    result = compare_periods(current, previous, current_label, previous_label)
    return jsonify(result)


@bp.post("/income-expenses")
@jwt_required()
def income_expenses():
    """Compare income vs expenses."""
    data = request.get_json() or {}
    income = float(data.get("income", 0))
    transactions = data.get("transactions", [])

    result = compare_income_expenses(income, transactions)
    return jsonify(result)
