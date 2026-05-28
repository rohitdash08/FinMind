"""Natural Language Finance Query API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.nl_finance_query import NLFinanceQueryService

bp = Blueprint("nl_finance_query", __name__)


@bp.post("/query")
@jwt_required()
def execute_query():
    """Execute a natural language finance query."""
    data = request.get_json() or {}
    query = data.get("query", "")
    transactions = data.get("transactions", [])

    service = NLFinanceQueryService()
    result = service.execute_query(query, transactions)
    return jsonify(result)


@bp.post("/parse")
@jwt_required()
def parse_query():
    """Parse a natural language query without executing."""
    data = request.get_json() or {}
    query = data.get("query", "")

    service = NLFinanceQueryService()
    parsed = service.parse_query(query)
    return jsonify({"parsed": parsed.to_dict()})
