"""
Recurring transaction anomaly alert endpoints.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import RecurringExpense, Expense
from ..services.recurring_anomaly import (
    RecurringConfig,
    ExpenseRecord,
    analyze_recurring_expense,
    batch_analyze,
    anomaly_summary,
    AMOUNT_DEVIATION_THRESHOLD,
    AMOUNT_LARGE_DEVIATION,
)
import logging

bp = Blueprint("recurring_anomaly", __name__)
logger = logging.getLogger("finmind.recurring_anomaly")


def _build_config(rec: RecurringExpense) -> RecurringConfig:
    return RecurringConfig(
        id=rec.id,
        expected_amount=rec.amount,
        cadence=rec.cadence.value if hasattr(rec.cadence, "value") else rec.cadence,
        active=rec.active,
        notes=rec.notes or "",
    )


def _load_expense_records(user_id: int, recurring_id: int | None = None) -> dict[int, list[ExpenseRecord]]:
    """Load expenses grouped by source_recurring_id."""
    q = (
        db.session.query(Expense)
        .filter_by(user_id=user_id)
        .filter(Expense.source_recurring_id.isnot(None))
    )
    if recurring_id is not None:
        q = q.filter_by(source_recurring_id=recurring_id)

    by_id: dict[int, list[ExpenseRecord]] = {}
    for exp in q.all():
        rid = exp.source_recurring_id
        by_id.setdefault(rid, []).append(
            ExpenseRecord(
                id=exp.id,
                amount=Decimal(str(exp.amount)),
                date=exp.spent_at.date() if hasattr(exp.spent_at, "date") else exp.spent_at,
                recurring_id=rid,
                notes=exp.notes or "",
            )
        )
    return by_id


@bp.get("")
@jwt_required()
def list_anomalies():
    """
    GET /api/recurring/anomalies
    Scan all active recurring expenses for the current user and return anomalies.

    Query params:
      - severity: low|medium|high|critical (filter)
      - type: amount|missing|frequency|timing (filter)
    """
    uid = int(get_jwt_identity())
    severity_filter = request.args.get("severity")
    type_filter = request.args.get("type")

    recurring = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=uid, active=True)
        .all()
    )
    if not recurring:
        return jsonify({"anomalies": [], "summary": anomaly_summary([])})

    configs = [_build_config(r) for r in recurring]
    expenses_map = _load_expense_records(uid)

    batch = batch_analyze(configs, expenses_map)

    all_anomalies = [a for alerts in batch.values() for a in alerts]

    # Apply filters
    if severity_filter:
        all_anomalies = [a for a in all_anomalies if a.severity == severity_filter]
    if type_filter:
        all_anomalies = [a for a in all_anomalies if a.anomaly_type == type_filter]

    # Sort by severity desc
    sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    all_anomalies.sort(key=lambda a: sev_order.get(a.severity, 0), reverse=True)

    logger.info("Anomaly scan user=%s found=%s", uid, len(all_anomalies))
    return jsonify({
        "anomalies": [a.to_dict() for a in all_anomalies],
        "summary": anomaly_summary(all_anomalies),
    })


@bp.get("/<int:recurring_id>")
@jwt_required()
def get_anomalies_for_recurring(recurring_id: int):
    """
    GET /api/recurring/anomalies/<recurring_id>
    Check anomalies for a specific recurring expense.
    """
    uid = int(get_jwt_identity())

    rec = db.session.query(RecurringExpense).filter_by(id=recurring_id, user_id=uid).first()
    if rec is None:
        return jsonify(error="Recurring expense not found"), 404

    config = _build_config(rec)
    expenses_map = _load_expense_records(uid, recurring_id=recurring_id)
    expenses = expenses_map.get(recurring_id, [])

    anomalies = analyze_recurring_expense(config, expenses)

    return jsonify({
        "recurring_id": recurring_id,
        "anomalies": [a.to_dict() for a in anomalies],
        "summary": anomaly_summary(anomalies),
        "expense_count_analyzed": len(expenses),
    })


@bp.get("/thresholds")
@jwt_required()
def get_thresholds():
    """
    GET /api/recurring/anomalies/thresholds
    Returns current detection thresholds.
    """
    return jsonify({
        "amount_deviation_threshold": AMOUNT_DEVIATION_THRESHOLD,
        "amount_large_deviation": AMOUNT_LARGE_DEVIATION,
        "description": {
            "amount_deviation_threshold": f">{AMOUNT_DEVIATION_THRESHOLD*100:.0f}% amount change triggers anomaly",
            "amount_large_deviation": f">{AMOUNT_LARGE_DEVIATION*100:.0f}% amount change triggers critical anomaly",
        },
    })