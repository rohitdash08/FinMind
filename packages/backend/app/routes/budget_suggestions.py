"""
Dynamic Budget Suggestions routes (Issue #73).

Endpoints:
  GET /budget/suggestions  → per-category suggested limits + confidence
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.budget_suggestions import get_budget_suggestions

bp = Blueprint("budget_suggestions", __name__)
logger = logging.getLogger("finmind.budget_suggestions_routes")


@bp.get("/suggestions")
@jwt_required()
def suggestions():
    """
    Return personalized monthly budget limits per spending category.

    Algorithm:
    1. Collect actual spending per category over 3–6 months
    2. Remove outlier months to build a clean baseline
    3. Suggest (baseline_avg × (1 − reduction_pct/100)) per category
    4. Score confidence: high / medium / low based on data richness + variance

    Query params:
        months        (int, 3-6, default 3)  — look-back window
        reduction_pct (float, 0-50, default 10) — % below average to target
        anchor        (YYYY-MM-DD, optional) — end month for analysis

    Response:
        suggestions       — list of per-category suggestions, sorted by
                            saving_opportunity descending
        total_suggested   — sum of all suggested limits
        income_summary    — avg income + 50/30/20 targets
        overall_confidence — weighted average confidence score (0–1)
        data_months_used  — effective months with data
        generated_at
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "3")
    try:
        months = int(months_raw)
        if not (3 <= months <= 6):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 3 and 6"), 400

    reduction_raw = request.args.get("reduction_pct", "10")
    try:
        reduction_pct = float(reduction_raw)
        if not (0.0 <= reduction_pct <= 50.0):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="reduction_pct must be a number between 0 and 50"), 400

    anchor = None
    if request.args.get("anchor"):
        try:
            anchor = date.fromisoformat(request.args["anchor"])
        except ValueError:
            return jsonify(error="anchor must be a valid ISO date (YYYY-MM-DD)"), 400

    result = get_budget_suggestions(uid, months=months, reduction_pct=reduction_pct, anchor=anchor)
    return jsonify(result)
