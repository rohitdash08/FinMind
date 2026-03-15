"""Spending classification routes.

Provides endpoints for essential vs discretionary spending
classification, breakdown analysis, and trend tracking.
"""

from datetime import date, datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import SpendingClass
from ..services.spending_class import (
    auto_classify_categories,
    set_category_class,
    get_categories_by_class,
    get_spending_breakdown,
    get_spending_trend,
)

bp = Blueprint("spending_class", __name__)

VALID_CLASSES = {c.value for c in SpendingClass}


@bp.route("/auto-classify", methods=["POST"])
@jwt_required()
def auto_classify():
    """Auto-classify all unclassified categories using keyword matching."""
    user_id = int(get_jwt_identity())
    result = auto_classify_categories(user_id)
    return jsonify({"classified": result}), 200


@bp.route("/categories/<int:category_id>", methods=["PUT"])
@jwt_required()
def update_category_class(category_id: int):
    """Manually set spending class for a category.

    Body:
        spending_class: ESSENTIAL, DISCRETIONARY, or UNCLASSIFIED
    """
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    spending_class = data.get("spending_class", "").upper()

    if spending_class not in VALID_CLASSES:
        return jsonify({
            "error": f"Invalid spending_class. Use: {', '.join(sorted(VALID_CLASSES))}"
        }), 400

    result = set_category_class(user_id, category_id, spending_class)
    if result is None:
        return jsonify({"error": "Category not found"}), 404

    return jsonify(result), 200


@bp.route("/categories", methods=["GET"])
@jwt_required()
def list_categories_by_class():
    """Get all categories grouped by spending class."""
    user_id = int(get_jwt_identity())
    result = get_categories_by_class(user_id)
    return jsonify(result), 200


@bp.route("/breakdown", methods=["GET"])
@jwt_required()
def breakdown():
    """Get essential vs discretionary spending breakdown.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD, default: 30 days ago)
        end_date: End date (YYYY-MM-DD, default: today)
    """
    user_id = int(get_jwt_identity())
    start_date = _parse_date(request.args.get("start_date"))
    end_date = _parse_date(request.args.get("end_date"))
    result = get_spending_breakdown(user_id, start_date, end_date)
    return jsonify(result), 200


@bp.route("/trend", methods=["GET"])
@jwt_required()
def trend():
    """Get monthly spending trend by class.

    Query Parameters:
        months: Number of months (default: 6, max: 24)
    """
    user_id = int(get_jwt_identity())
    months = request.args.get("months", 6, type=int)
    if months < 1 or months > 24:
        return jsonify({"error": "months must be between 1 and 24"}), 400

    result = get_spending_trend(user_id, months)
    return jsonify({"trend": result}), 200


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
