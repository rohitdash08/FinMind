"""
Explainable Spending Insights routes (Issue #89).

Endpoints:
  GET /insights/explain         → full explainable insights (MoM changes + why)
  GET /insights/explain/summary → top changes + overall trend only (lightweight)
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.spending_insights import get_spending_insights

bp = Blueprint("insights_explainable", __name__)
logger = logging.getLogger("finmind.insights_explainable_routes")


@bp.get("/explain")
@jwt_required()
def explain():
    """
    Return explainable month-over-month spending insights.

    For each consecutive pair of months in the window, surfaces:
    - Which categories changed significantly
    - What changed (direction + magnitude)
    - Why it changed (pattern-based explanation)
    - Confidence level (high / medium / low)

    Query params:
        months (int, 2-12, default 3) — analysis window
        anchor (YYYY-MM-DD, default today)

    Response:
        insights         — per-period list of category changes with explanations
        top_changes      — top 3 largest changes across all periods
        overall_trend    — 'increasing' | 'decreasing' | 'stable' | 'insufficient_data'
        trend_confidence — confidence in overall trend
        period_summaries — per-month income/expense/net
        generated_at
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "3")
    try:
        months = int(months_raw)
        if not (2 <= months <= 12):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 2 and 12"), 400

    anchor = None
    if request.args.get("anchor"):
        try:
            anchor = date.fromisoformat(request.args["anchor"])
        except ValueError:
            return jsonify(error="anchor must be a valid ISO date (YYYY-MM-DD)"), 400

    result = get_spending_insights(uid, months=months, anchor=anchor)
    return jsonify(result)


@bp.get("/explain/summary")
@jwt_required()
def explain_summary():
    """
    Lightweight version: top changes + overall trend only.
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "3")
    try:
        months = int(months_raw)
        if not (2 <= months <= 12):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 2 and 12"), 400

    full = get_spending_insights(uid, months=months)
    return jsonify({
        "top_changes":      full["top_changes"],
        "overall_trend":    full["overall_trend"],
        "trend_confidence": full["trend_confidence"],
        "generated_at":     full["generated_at"],
    })
