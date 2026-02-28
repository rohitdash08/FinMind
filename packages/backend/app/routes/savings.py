"""Savings opportunity detection routes."""

from flask import Blueprint, jsonify, request
from app.services.savings_detection import detect_opportunities

bp = Blueprint("savings", __name__)


@bp.route("/opportunities", methods=["POST"])
def find_opportunities():
    """Detect savings opportunities from spending data.

    Body: {
        "expenses": [{"amount": 15, "category_name": "streaming", "notes": "Netflix", "spent_at": "2026-02-01"}],
        "bills": [{"name": "Internet", "amount": 80, "cadence": "MONTHLY"}],
        "lookback_days": 90
    }
    """
    data = request.get_json() or {}
    expenses = data.get("expenses", [])
    if not expenses:
        return jsonify({"error": "expenses list is required"}), 400

    bills = data.get("bills", [])
    lookback_days = data.get("lookback_days", 90)

    result = detect_opportunities(expenses, bills=bills, lookback_days=lookback_days)
    return jsonify(result)
