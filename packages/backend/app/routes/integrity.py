"""
Financial Data Integrity & Reconciliation routes (Issue #96).

Endpoints:
  GET /integrity/check           → run full integrity check
  GET /integrity/reconciliation  → per-month reconciliation summary only
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.integrity import run_integrity_check

bp = Blueprint("integrity", __name__)
logger = logging.getLogger("finmind.integrity_routes")


@bp.get("/check")
@jwt_required()
def check():
    """
    Run a full financial data integrity check.

    Query params:
        months (int, 1-12, default 3) — analysis window
        anchor (YYYY-MM-DD, default today)

    Response:
        alerts           — list of integrity alerts with severity + suggestion
        alert_counts     — {high, medium, low, total}
        reconciliation   — per-month income/expense/net_flow
        analysis_months  — int
        healthy          — bool (True when no high-severity alerts)
        generated_at     — ISO timestamp

    Alert types:
        orphan_category         — expense references a deleted category
        duplicate_expense       — identical amount+date+notes recorded multiple times
        missing_recurring_instance — active recurring with no transaction in a period
        negative_net_flow       — expenses exceeded income in a month
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "3")
    try:
        months = int(months_raw)
        if not (1 <= months <= 12):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 12"), 400

    anchor = None
    if request.args.get("anchor"):
        try:
            anchor = date.fromisoformat(request.args["anchor"])
        except ValueError:
            return jsonify(error="anchor must be a valid ISO date (YYYY-MM-DD)"), 400

    result = run_integrity_check(uid, months=months, anchor=anchor)
    return jsonify(result)


@bp.get("/reconciliation")
@jwt_required()
def reconciliation():
    """
    Return only the per-month reconciliation summary (lightweight).

    Query params: months (1-12, default 3)
    """
    uid = int(get_jwt_identity())

    months_raw = request.args.get("months", "3")
    try:
        months = int(months_raw)
        if not (1 <= months <= 12):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 12"), 400

    full = run_integrity_check(uid, months=months)
    return jsonify({
        "reconciliation": full["reconciliation"],
        "analysis_months": months,
        "generated_at": full["generated_at"],
    })
