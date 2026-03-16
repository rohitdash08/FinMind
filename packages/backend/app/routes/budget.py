"""
Autonomous Budget Optimization routes (Issue #92).

Endpoints:
  GET /budget/optimize         → analyse spending & return reallocation plan
  GET /budget/optimize/summary → lightweight summary (trend + net flow only)
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.budget_optimizer import get_budget_optimization

bp = Blueprint("budget", __name__)
logger = logging.getLogger("finmind.budget")


@bp.get("/optimize")
@jwt_required()
def optimize():
    """
    Return a full autonomous budget optimization plan for the authenticated user.

    Query params:
        months (int, 1-12, default 3) — how many months of history to analyse
        anchor (YYYY-MM-DD, default today) — end date for the analysis window

    Response keys:
        analysis_period_months, monthly_breakdown, avg_monthly_expenses,
        avg_monthly_income, net_flow, trend, overspending_alerts,
        category_totals, recommendations, generated_at
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "3")
    try:
        months = int(months_raw)
        if not (1 <= months <= 12):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 12"), 400

    anchor_raw = request.args.get("anchor")
    anchor = None
    if anchor_raw:
        try:
            anchor = date.fromisoformat(anchor_raw)
        except ValueError:
            return jsonify(error="anchor must be a valid ISO date (YYYY-MM-DD)"), 400

    result = get_budget_optimization(uid, months=months, anchor=anchor)
    return jsonify(result)


@bp.get("/optimize/summary")
@jwt_required()
def optimize_summary():
    """
    Return a lightweight budget summary: trend direction, net flow, and top
    recommendations only.  Faster than the full /optimize endpoint.
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "3")
    try:
        months = int(months_raw)
        if not (1 <= months <= 12):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 12"), 400

    full = get_budget_optimization(uid, months=months)
    summary = {
        "trend": full["trend"],
        "net_flow": full["net_flow"],
        "avg_monthly_expenses": full["avg_monthly_expenses"],
        "avg_monthly_income": full["avg_monthly_income"],
        "overspending_alert_count": len(full["overspending_alerts"]),
        "top_recommendations": full["recommendations"][:3],
        "generated_at": full["generated_at"],
    }
    return jsonify(summary)
