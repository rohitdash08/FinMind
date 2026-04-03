"""Financial Data Integrity & Reconciliation routes for FinMind (#96)."""
import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.integrity import run_integrity_check, get_reconciliation_summary

bp = Blueprint("integrity", __name__)
logger = logging.getLogger("finmind.integrity_routes")


@bp.get("/check")
@jwt_required()
def integrity_check():
    """
    Run all data integrity checks for the current user.

    Returns a report with all detected issues categorized by type and severity.
    Types: duplicate_expense, balance_mismatch, missing_category,
           large_amount, future_date, orphaned_recurring

    Returns:
        { "total_issues": int, "alerts": [...], "summary": {...}, "checked_at": "YYYY-MM-DD" }
    """
    uid = int(get_jwt_identity())
    result = run_integrity_check(uid)
    logger.info("Integrity check uid=%s total_issues=%s", uid, result["total_issues"])
    return jsonify(result)


@bp.get("/reconciliation")
@jwt_required()
def reconciliation():
    """
    Get monthly reconciliation summary showing income/expense/net balance.

    Query params:
        months (int, 1-12, default 3): Number of months to summarize

    Returns:
        { "months": [...], "totals": {...}, "period_months": int }
    """
    uid = int(get_jwt_identity())
    try:
        months = int(request.args.get("months", 3))
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 12"), 400

    if not (1 <= months <= 12):
        return jsonify(error="months must be between 1 and 12"), 400

    result = get_reconciliation_summary(uid, months)
    logger.info("Reconciliation uid=%s months=%s", uid, months)
    return jsonify(result)

