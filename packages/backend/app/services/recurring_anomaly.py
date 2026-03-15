"""Recurring transaction anomaly detection service.

Monitors recurring expenses for unexpected amount changes by comparing
actual charges against historical snapshots. Generates alerts when
deviations exceed configurable thresholds.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import desc, func

from app.extensions import db
from app.models import (
    RecurringExpense,
    Expense,
    RecurringExpenseSnapshot,
    RecurringAnomalyAlert,
)


# Default threshold: alert if amount deviates > 10%
DEFAULT_THRESHOLD_PCT = 10.0


# ── Snapshot Management ───────────────────────────────────────────


def record_snapshot(recurring_id: int, amount: Decimal) -> dict:
    """Record a price snapshot for a recurring expense."""
    snapshot = RecurringExpenseSnapshot(
        recurring_id=recurring_id,
        amount=amount,
    )
    db.session.add(snapshot)
    db.session.commit()
    return _serialize_snapshot(snapshot)


def get_snapshots(recurring_id: int, limit: int = 20) -> list:
    """Get historical snapshots for a recurring expense."""
    records = (
        RecurringExpenseSnapshot.query
        .filter_by(recurring_id=recurring_id)
        .order_by(desc(RecurringExpenseSnapshot.recorded_at))
        .limit(limit)
        .all()
    )
    return [_serialize_snapshot(r) for r in records]


def get_expected_amount(recurring_id: int) -> Optional[Decimal]:
    """Get the expected (most recent snapshot) amount.

    Falls back to the recurring expense's configured amount if no snapshots.
    """
    latest = (
        RecurringExpenseSnapshot.query
        .filter_by(recurring_id=recurring_id)
        .order_by(desc(RecurringExpenseSnapshot.recorded_at))
        .first()
    )
    if latest:
        return latest.amount

    recurring = RecurringExpense.query.get(recurring_id)
    if recurring:
        return recurring.amount
    return None


# ── Anomaly Detection ─────────────────────────────────────────────


def check_anomaly(
    recurring_id: int,
    actual_amount: Decimal,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
) -> dict:
    """Check if a transaction amount is anomalous.

    Compares actual_amount against expected amount. If deviation
    exceeds threshold, creates an alert and returns anomaly info.
    """
    expected = get_expected_amount(recurring_id)
    if expected is None:
        return {"error": "Recurring expense not found"}

    expected_f = float(expected)
    actual_f = float(actual_amount)

    if expected_f == 0:
        deviation_pct = 100.0 if actual_f != 0 else 0.0
    else:
        deviation_pct = round(abs(actual_f - expected_f) / expected_f * 100, 2)

    is_anomaly = deviation_pct > threshold_pct

    result = {
        "recurring_id": recurring_id,
        "expected_amount": expected_f,
        "actual_amount": actual_f,
        "deviation_pct": deviation_pct,
        "threshold_pct": threshold_pct,
        "is_anomaly": is_anomaly,
    }

    if is_anomaly:
        recurring = RecurringExpense.query.get(recurring_id)
        if recurring:
            alert_type = "amount_increase" if actual_f > expected_f else "amount_decrease"
            alert = RecurringAnomalyAlert(
                user_id=recurring.user_id,
                recurring_id=recurring_id,
                expected_amount=expected,
                actual_amount=actual_amount,
                deviation_pct=deviation_pct,
                alert_type=alert_type,
            )
            db.session.add(alert)
            db.session.commit()
            result["alert_id"] = alert.id
            result["alert_type"] = alert_type

    # Record snapshot for future reference
    record_snapshot(recurring_id, actual_amount)

    return result


def scan_all_recurring(user_id: int, threshold_pct: float = DEFAULT_THRESHOLD_PCT) -> dict:
    """Scan all active recurring expenses for anomalies.

    Compares each recurring expense's current amount against its
    most recent snapshot. Returns summary with any detected anomalies.
    """
    recurring_list = RecurringExpense.query.filter_by(
        user_id=user_id, active=True
    ).all()

    anomalies = []
    checked = 0

    for rec in recurring_list:
        expected = get_expected_amount(rec.id)
        if expected is None:
            continue

        checked += 1
        expected_f = float(expected)
        current_f = float(rec.amount)

        if expected_f == 0:
            deviation = 100.0 if current_f != 0 else 0.0
        else:
            deviation = round(abs(current_f - expected_f) / expected_f * 100, 2)

        if deviation > threshold_pct:
            alert_type = "amount_increase" if current_f > expected_f else "amount_decrease"
            alert = RecurringAnomalyAlert(
                user_id=user_id,
                recurring_id=rec.id,
                expected_amount=expected,
                actual_amount=rec.amount,
                deviation_pct=deviation,
                alert_type=alert_type,
            )
            db.session.add(alert)
            anomalies.append({
                "recurring_id": rec.id,
                "notes": rec.notes,
                "expected_amount": expected_f,
                "actual_amount": current_f,
                "deviation_pct": deviation,
                "alert_type": alert_type,
            })

    if anomalies:
        db.session.commit()

    return {
        "total_checked": checked,
        "anomalies_found": len(anomalies),
        "anomalies": anomalies,
        "threshold_pct": threshold_pct,
    }


# ── Alert Management ──────────────────────────────────────────────


def get_alerts(
    user_id: int,
    unacknowledged_only: bool = False,
    limit: int = 50,
) -> list:
    """Get anomaly alerts for a user."""
    query = RecurringAnomalyAlert.query.filter_by(user_id=user_id)
    if unacknowledged_only:
        query = query.filter_by(acknowledged=False)
    records = (
        query.order_by(desc(RecurringAnomalyAlert.created_at))
        .limit(limit)
        .all()
    )
    return [_serialize_alert(r) for r in records]


def acknowledge_alert(user_id: int, alert_id: int) -> dict:
    """Acknowledge a single alert."""
    alert = RecurringAnomalyAlert.query.filter_by(
        id=alert_id, user_id=user_id
    ).first()
    if not alert:
        return {"error": "Alert not found"}
    alert.acknowledged = True
    db.session.commit()
    return _serialize_alert(alert)


def acknowledge_all_alerts(user_id: int) -> dict:
    """Acknowledge all pending alerts."""
    count = (
        RecurringAnomalyAlert.query
        .filter_by(user_id=user_id, acknowledged=False)
        .update({"acknowledged": True})
    )
    db.session.commit()
    return {"acknowledged_count": count}


def get_anomaly_summary(user_id: int) -> dict:
    """Get a summary of anomalies for a user.

    Returns counts by type and severity.
    """
    alerts = RecurringAnomalyAlert.query.filter_by(user_id=user_id).all()

    if not alerts:
        return {
            "total_alerts": 0,
            "unacknowledged": 0,
            "by_type": {},
            "avg_deviation_pct": 0,
            "max_deviation_pct": 0,
        }

    unacked = sum(1 for a in alerts if not a.acknowledged)
    by_type = {}
    deviations = []

    for a in alerts:
        by_type[a.alert_type] = by_type.get(a.alert_type, 0) + 1
        deviations.append(float(a.deviation_pct))

    return {
        "total_alerts": len(alerts),
        "unacknowledged": unacked,
        "by_type": by_type,
        "avg_deviation_pct": round(sum(deviations) / len(deviations), 2),
        "max_deviation_pct": round(max(deviations), 2),
    }


# ── Serializers ───────────────────────────────────────────────────


def _serialize_snapshot(record: RecurringExpenseSnapshot) -> dict:
    return {
        "id": record.id,
        "recurring_id": record.recurring_id,
        "amount": float(record.amount),
        "recorded_at": record.recorded_at.isoformat() if record.recorded_at else None,
    }


def _serialize_alert(record: RecurringAnomalyAlert) -> dict:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "recurring_id": record.recurring_id,
        "expected_amount": float(record.expected_amount),
        "actual_amount": float(record.actual_amount),
        "deviation_pct": float(record.deviation_pct),
        "alert_type": record.alert_type,
        "acknowledged": record.acknowledged,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
