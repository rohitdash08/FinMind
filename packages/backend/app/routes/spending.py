"""Spending breakdown routes."""

from flask import Blueprint, jsonify, request
from app.services.spending_breakdown import (
    analyze_spending_breakdown,
    classify_category,
    get_monthly_trend,
    SpendingType,
)

bp = Blueprint("spending", __name__)


@bp.route("/breakdown", methods=["POST"])
def breakdown():
    """Analyze essential vs discretionary spending.

    Body: {"expenses": [{"amount": 100, "category_name": "groceries", "spent_at": "2026-02-01"}]}
    """
    data = request.get_json() or {}
    expenses = data.get("expenses", [])
    if not expenses:
        return jsonify({"error": "expenses list is required"}), 400
    custom_rules = data.get("custom_rules")
    result = analyze_spending_breakdown(expenses, custom_rules=custom_rules)
    return jsonify(result)


@bp.route("/classify", methods=["POST"])
def classify():
    """Classify a category name.

    Body: {"category_name": "groceries"}
    """
    data = request.get_json() or {}
    name = data.get("category_name")
    if not name:
        return jsonify({"error": "category_name is required"}), 400
    result = classify_category(name)
    return jsonify({"category_name": name, "type": result.value})


@bp.route("/trend", methods=["POST"])
def trend():
    """Get monthly essential vs discretionary trend.

    Body: {"expenses": [...], "months": 6}
    """
    data = request.get_json() or {}
    expenses = data.get("expenses", [])
    if not expenses:
        return jsonify({"error": "expenses list is required"}), 400
    months = data.get("months", 6)
    result = get_monthly_trend(expenses, months=months)
    return jsonify(result)
