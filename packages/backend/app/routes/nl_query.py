from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.nl_query import execute_nl_query, parse_date_range, extract_category

bp = Blueprint("nl_query", __name__, url_prefix="/query")


@bp.route("/", methods=["POST"])
@jwt_required()
def natural_language_query():
    """
    Accept a natural language finance query and return structured spending data.
    
    Body: {"query": "How much did I spend on food last quarter?"}
    """
    body = request.get_json(force=True) or {}
    query = body.get("query", "").strip()
    
    if not query:
        return jsonify({"error": "query is required"}), 400
    if len(query) > 500:
        return jsonify({"error": "query too long (max 500 chars)"}), 400
    
    user_id = int(get_jwt_identity())
    result = execute_nl_query(query, user_id)
    return jsonify(result), 200


@bp.route("/parse", methods=["POST"])
@jwt_required()
def parse_query():
    """
    Dry-run: parse a query and return interpreted date range and category
    without hitting the database.
    
    Body: {"query": "spending last month on food"}
    """
    body = request.get_json(force=True) or {}
    query = body.get("query", "").strip()
    
    if not query:
        return jsonify({"error": "query is required"}), 400
    
    from datetime import date
    start, end = parse_date_range(query)
    category = extract_category(query)
    
    return jsonify({
        "query": query,
        "interpreted": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "category": category,
        },
    }), 200
