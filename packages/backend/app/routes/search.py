"""Search API routes.

Provides endpoints for advanced search across expenses, bills,
and recurring expenses with filtering, pagination, and suggestions.
"""

from datetime import date, datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.search import advanced_search, search_suggestions, get_search_stats

bp = Blueprint("search", __name__)


@bp.route("", methods=["GET"])
@jwt_required()
def search():
    """Search across transactions, bills, and recurring expenses.

    Query Parameters:
        q: Search text (searches notes/names)
        category_id: Filter by category ID
        amount_min: Minimum amount
        amount_max: Maximum amount
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        expense_type: EXPENSE or INCOME
        types: Comma-separated entity types (expenses,bills,recurring)
        sort_by: Sort field (date, amount, name, type)
        sort_order: asc or desc
        page: Page number (default 1)
        page_size: Results per page (default 50, max 200)
    """
    user_id = int(get_jwt_identity())
    query = request.args.get("q", None)
    category_id = request.args.get("category_id", None, type=int)
    amount_min = request.args.get("amount_min", None, type=float)
    amount_max = request.args.get("amount_max", None, type=float)

    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))

    expense_type = request.args.get("expense_type", None)
    types_str = request.args.get("types", None)
    entity_types = types_str.split(",") if types_str else None

    sort_by = request.args.get("sort_by", "date")
    sort_order = request.args.get("sort_order", "desc")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 50, type=int)

    if sort_by not in ("date", "amount", "name", "type"):
        return jsonify({"error": "Invalid sort_by. Use: date, amount, name, type"}), 400
    if sort_order not in ("asc", "desc"):
        return jsonify({"error": "Invalid sort_order. Use: asc, desc"}), 400
    if page < 1:
        return jsonify({"error": "Page must be >= 1"}), 400
    if page_size < 1 or page_size > 200:
        return jsonify({"error": "page_size must be between 1 and 200"}), 400

    result = advanced_search(
        user_id=user_id,
        query=query,
        category_id=category_id,
        amount_min=amount_min,
        amount_max=amount_max,
        date_from=date_from,
        date_to=date_to,
        expense_type=expense_type,
        entity_types=entity_types,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    return jsonify(result), 200


@bp.route("/suggestions", methods=["GET"])
@jwt_required()
def suggestions():
    """Get search suggestions based on a prefix.

    Query Parameters:
        q: Search prefix (min 2 characters)
        limit: Maximum suggestions (default 10, max 50)
    """
    user_id = int(get_jwt_identity())
    prefix = request.args.get("q", "")
    limit = request.args.get("limit", 10, type=int)

    if limit < 1 or limit > 50:
        return jsonify({"error": "limit must be between 1 and 50"}), 400

    results = search_suggestions(user_id, prefix, limit)
    return jsonify({"suggestions": results}), 200


@bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    """Get search statistics for the current user."""
    user_id = int(get_jwt_identity())
    result = get_search_stats(user_id)
    return jsonify(result), 200


def _parse_date(value: str | None) -> date | None:
    """Parse a date string in YYYY-MM-DD format."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
