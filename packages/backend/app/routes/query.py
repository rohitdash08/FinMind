"""
Natural Language Query Routes
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.nlp_query import process_natural_language_query

bp = Blueprint("query", __name__, url_prefix="/query")


@bp.route("", methods=["POST"])
@jwt_required()
def natural_language_query():
    """
    POST /query
    Body: { "query": "How much did I spend on food last quarter?" }
    
    Returns:
    {
      "answer": "You spent 1234.56 INR on food from 2025-10-01 to 2025-12-31.",
      "total_amount": 1234.56,
      "currency": "INR",
      "transaction_count": 15,
      "date_range": {
        "start": "2025-10-01",
        "end": "2025-12-31"
      },
      "category": "food",
      "source_data": [...]
    }
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data or "query" not in data:
        return jsonify({"error": "Missing 'query' field"}), 400
    
    query = data["query"].strip()
    if not query:
        return jsonify({"error": "Query cannot be empty"}), 400
    
    try:
        result = process_natural_language_query(user_id, query)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
