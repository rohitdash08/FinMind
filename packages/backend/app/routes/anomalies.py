"""Recurring transaction anomaly detection & alerts."""

from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import AnomalyAlert, Expense, Category
import logging

bp = Blueprint("anomalies", __name__)
logger = logging.getLogger("finmind.anomalies")


def _alert_to_dict(a):
    return {
        "id": a.id, "alert_type": a.alert_type, "severity": a.severity,
        "message": a.message, "expense_id": a.expense_id,
        "acknowledged": a.acknowledged, "created_at": a.created_at.isoformat(),
    }


@bp.get("")
@jwt_required()
def list_alerts():
    uid = int(get_jwt_identity())
    only_unack = request.args.get("unacknowledged", "").lower() == "true"
    q = db.session.query(AnomalyAlert).filter_by(user_id=uid)
    if only_unack:
        q = q.filter_by(acknowledged=False)
    alerts = q.order_by(AnomalyAlert.created_at.desc()).limit(50).all()
    return jsonify([_alert_to_dict(a) for a in alerts])


@bp.post("/<int:alert_id>/acknowledge")
@jwt_required()
def acknowledge(alert_id):
    uid = int(get_jwt_identity())
    alert = db.session.get(AnomalyAlert, alert_id)
    if not alert or alert.user_id != uid:
        return jsonify(error="not found"), 404
    alert.acknowledged = True
    db.session.commit()
    return jsonify(_alert_to_dict(alert))


@bp.post("/scan")
@jwt_required()
def scan_anomalies():
    """Scan recent transactions for anomalies and generate alerts."""
    uid = int(get_jwt_identity())
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    recent = db.session.query(Expense).filter(
        Expense.user_id == uid, Expense.spent_at >= week_ago
    ).all()
    historical = db.session.query(Expense).filter(
        Expense.user_id == uid, Expense.spent_at >= month_ago, Expense.spent_at < week_ago
    ).all()

    alerts_created = []

    # 1. Large transaction detection (> 2x average)
    if historical:
        avg = sum(float(e.amount) for e in historical) / len(historical)
        threshold = max(avg * 2, 100)
        for e in recent:
            if float(e.amount) > threshold:
                alert = _create_alert(uid, "large_transaction", "high",
                    f"Transaction of {float(e.amount):.2f} is {float(e.amount)/avg:.1f}x your average ({avg:.2f})",
                    e.id)
                if alert:
                    alerts_created.append(alert)

    # 2. Spending spike (weekly total > 1.5x previous week average)
    if historical:
        weekly_avg = sum(float(e.amount) for e in historical) / max(1, (month_ago - week_ago).days / 7)
        weekly_total = sum(float(e.amount) for e in recent)
        if weekly_total > weekly_avg * 1.5 and weekly_avg > 0:
            alert = _create_alert(uid, "spike", "medium",
                f"This week's spending ({weekly_total:.2f}) is {weekly_total/weekly_avg:.1f}x your weekly average ({weekly_avg:.2f})")
            if alert:
                alerts_created.append(alert)

    # 3. Unusual frequency (> 3 transactions per day)
    from collections import Counter
    daily_counts = Counter(e.spent_at for e in recent)
    for day, count in daily_counts.items():
        if count > 3:
            alert = _create_alert(uid, "frequency", "low",
                f"{count} transactions on {day.isoformat()} - unusually high activity")
            if alert:
                alerts_created.append(alert)

    db.session.commit()
    return jsonify(
        alerts_created=len(alerts_created),
        alerts=[_alert_to_dict(a) for a in alerts_created],
    )


def _create_alert(uid, alert_type, severity, message, expense_id=None):
    existing = db.session.query(AnomalyAlert).filter_by(
        user_id=uid, message=message, acknowledged=False
    ).first()
    if existing:
        return None
    alert = AnomalyAlert(
        user_id=uid, alert_type=alert_type, severity=severity,
        message=message, expense_id=expense_id,
    )
    db.session.add(alert)
    db.session.flush()
    return alert
