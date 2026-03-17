"""
Natural Language Finance Query routes (Issue #74).

Endpoints:
  POST /query/ask   → answer a natural language finance question
  GET  /query/examples → return example queries the engine supports
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.nl_query import answer_query

bp = Blueprint("nl_query", __name__)
logger = logging.getLogger("finmind.nl_query_routes")

_EXAMPLES = [
    "How much did I spend on food last month?",
    "What were my total expenses last quarter?",
    "How much did I earn this year?",
    "What is my net flow for last month?",
    "How many transactions did I have last week?",
    "Show my top spending categories this month.",
    "What is my average spending in March?",
    "How much did I spend on transport in 2026?",
    "What did I spend on dining last week?",
    "How much did I save last year?",
]


@bp.post("/ask")
@jwt_required()
def ask():
    """
    Answer a natural language finance question.

    Request body:
        query  (str, required) — the natural language question
        anchor (YYYY-MM-DD, optional) — reference date (defaults to today)

    Response:
        query, intent, date_range, category, answer, answer_text,
        source_data, confidence
    """
    uid  = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    query = str(data.get("query") or "").strip()
    if not query:
        return jsonify(error="'query' is required"), 400
    if len(query) > 500:
        return jsonify(error="query must be 500 characters or less"), 400

    anchor = None
    if data.get("anchor"):
        try:
            anchor = date.fromisoformat(str(data["anchor"]))
        except ValueError:
            return jsonify(error="anchor must be a valid ISO date (YYYY-MM-DD)"), 400

    result = answer_query(uid, query, anchor=anchor)
    return jsonify(result)


@bp.get("/examples")
@jwt_required()
def examples():
    """Return example queries the engine understands."""
    return jsonify({"examples": _EXAMPLES})
