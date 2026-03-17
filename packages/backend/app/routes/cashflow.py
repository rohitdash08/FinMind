"""
Advanced Cash Flow Forecasting routes (Issue #93).

Endpoints:
  GET /cashflow/forecast   → generate a cash flow forecast
  GET /cashflow/summary    → lightweight summary (no month-by-month breakdown)
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.cashflow import forecast_cashflow

bp = Blueprint("cashflow", __name__)
logger = logging.getLogger("finmind.cashflow_routes")


@bp.get("/forecast")
@jwt_required()
def forecast():
    """
    Generate a month-by-month cash flow forecast.

    Query params:
        months (int, 1-24, default 6)  — forecast horizon
        anchor (YYYY-MM-DD, optional)  — start date (defaults to today)

    Response:
        forecasts        — list of monthly forecasted states:
                           {month, projected_income, projected_expenses,
                            bill_obligations, projected_net, seasonal_index,
                            income_range, expense_range, likely_tight}
        irregular_months — list of historical months with one-off spikes
                           (excluded from baseline calculation)
        upcoming_bills   — {YYYY-MM: total} known bill obligations
        confidence       — high | medium | low
        data_months_used — months of history available
        summary          — {avg_projected_income, avg_projected_expenses,
                            avg_projected_net, positive_months, negative_months}
        generated_at     — ISO timestamp
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "6")
    try:
        months = int(months_raw)
        if not (1 <= months <= 24):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 24"), 400

    anchor = None
    if request.args.get("anchor"):
        try:
            anchor = date.fromisoformat(request.args["anchor"])
        except ValueError:
            return jsonify(error="anchor must be a valid ISO date (YYYY-MM-DD)"), 400

    result = forecast_cashflow(uid, horizon_months=months, anchor=anchor)
    return jsonify(result)


@bp.get("/summary")
@jwt_required()
def summary():
    """
    Return a lightweight cash flow summary without the full month-by-month breakdown.

    Query params: months (1-24, default 6)
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "6")
    try:
        months = int(months_raw)
        if not (1 <= months <= 24):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 24"), 400

    full = forecast_cashflow(uid, horizon_months=months)
    return jsonify({
        "summary":           full["summary"],
        "confidence":        full["confidence"],
        "data_months_used":  full["data_months_used"],
        "irregular_months":  full["irregular_months"],
        "horizon_months":    months,
        "generated_at":      full["generated_at"],
    })
