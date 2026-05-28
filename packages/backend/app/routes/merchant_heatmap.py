"""Merchant heatmap API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.merchant_heatmap import generate_merchant_heatmap, get_merchant_patterns

bp = Blueprint("merchant_heatmap", __name__)


@bp.post("/heatmap")
@jwt_required()
def heatmap():
    """Generate merchant spending frequency heatmap."""
    data = request.get_json() or {}
    transactions = data.get("transactions", [])
    group_by = data.get("group_by", "day_of_week")
    top_n = data.get("top_n", 10)

    result = generate_merchant_heatmap(transactions, group_by=group_by, top_n=top_n)
    return jsonify(result)


@bp.post("/patterns")
@jwt_required()
def patterns():
    """Detect spending patterns per merchant."""
    data = request.get_json() or {}
    transactions = data.get("transactions", [])

    result = get_merchant_patterns(transactions)
    return jsonify(result)
