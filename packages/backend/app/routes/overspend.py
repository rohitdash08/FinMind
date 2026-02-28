"""Overspend warning routes."""

from flask import Blueprint, jsonify, request
from app.services.overspend_warning import check_overspend

bp = Blueprint("overspend", __name__)


@bp.route("/check", methods=["POST"])
def check():
    """Check spending against budgets.

    Body: {
        "expenses": [{"amount": 50, "category_name": "dining", "spent_at": "2026-02-15"}],
        "budgets": {"dining": 200, "groceries": 400},
        "period_start": "2026-02-01",
        "period_end": "2026-02-28"
    }
    """
    data = request.get_json() or {}
    expenses = data.get("expenses", [])
    budgets = data.get("budgets", {})
    if not budgets:
        return jsonify({"error": "budgets dict is required"}), 400

    result = check_overspend(
        expenses,
        budgets,
        period_start=data.get("period_start"),
        period_end=data.get("period_end"),
    )
    return jsonify(result)
