"""Lifestyle inflation detection routes."""

from flask import Blueprint, jsonify, request
from app.services.lifestyle_inflation import detect_lifestyle_inflation

bp = Blueprint("lifestyle", __name__)


@bp.route("/inflation", methods=["POST"])
def check_inflation():
    """Detect lifestyle inflation from spending history.

    Body: {
        "expenses": [{"amount": 100, "category_name": "dining", "spent_at": "2026-01-15"}],
        "income_monthly": 5000,
        "months": 6
    }
    """
    data = request.get_json() or {}
    expenses = data.get("expenses", [])
    if not expenses:
        return jsonify({"error": "expenses list is required"}), 400

    income = data.get("income_monthly")
    months = data.get("months", 6)

    result = detect_lifestyle_inflation(expenses, income_monthly=income, months=months)
    return jsonify(result)
