"""Explainable spending insights API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.explainable import generate_insights, get_spending_summary

bp = Blueprint("insights_explain", __name__)


@bp.post("/explain")
@jwt_required()
def explain_spending():
    """Generate explainable spending insights.

    Expects JSON body with:
    - current: list of transaction dicts for current period
    - previous: list of transaction dicts for previous period
    - period_label: optional label (default "this period")
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    current = data.get("current", [])
    previous = data.get("previous", [])
    label = data.get("period_label", "this period")

    if not current and not previous:
        return jsonify({"error": "No transaction data provided"}), 400

    insights = generate_insights(current, previous, label)

    return jsonify({
        "insights": [i.to_dict() for i in insights],
        "current_summary": get_spending_summary(current),
        "previous_summary": get_spending_summary(previous),
        "total_insights": len(insights),
    })


@bp.post("/summary")
@jwt_required()
def spending_summary():
    """Get spending summary for a set of transactions."""
    data = request.get_json() or {}
    transactions = data.get("transactions", [])
    return jsonify(get_spending_summary(transactions))
