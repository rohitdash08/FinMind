"""
Financial Data Integrity & Reconciliation routes (Issue #96).

Endpoints:
  GET /integrity/check          → full integrity report
  GET /integrity/check/summary  → lightweight status + counts only
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.integrity import run_integrity_check

bp = Blueprint("integrity", __name__)
logger = logging.getLogger("finmind.integrity")


@bp.get("/check")
@jwt_required()
def integrity_check():
    """
    Run a full financial data integrity check for the authenticated user.

    Query params:
        months (int, 1-12, default 3) — look-back window for balance mismatch check

    Response keys:
        overall_status, total_issues, balance_mismatches, orphaned_expenses,
        orphaned_recurring, future_dated_expenses, duplicate_expenses,
        negative_amounts, stale_recurring, bills_missing_reminders,
        analysis_months, generated_at
    """
    uid = int(get_jwt_identity())
    months_raw = request.args.get("months", "3")
    try:
        months = int(months_raw)
        if not (1 <= months <= 12):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 12"), 400

    report = run_integrity_check(uid, months=months)
    return jsonify(report)


@bp.get("/check/summary")
@jwt_required()
def integrity_summary():
    """
    Return a lightweight integrity summary: overall status and per-check counts.
    Faster than the full report — useful for dashboard badges.
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
        "overall_status": full["overall_status"],
        "total_issues": full["total_issues"],
        "counts": {
            "balance_mismatches": len(full["balance_mismatches"]),
            "orphaned_expenses": len(full["orphaned_expenses"]),
            "orphaned_recurring": len(full["orphaned_recurring"]),
            "future_dated_expenses": len(full["future_dated_expenses"]),
            "duplicate_expenses": len(full["duplicate_expenses"]),
            "negative_amounts": len(full["negative_amounts"]),
            "stale_recurring": len(full["stale_recurring"]),
            "bills_missing_reminders": len(full["bills_missing_reminders"]),
        },
        "generated_at": full["generated_at"],
    })
