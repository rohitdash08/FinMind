from datetime import date, timedelta
from decimal import Decimal
from ..extensions import db
from ..models import AnomalyAlert, Expense, RecurringExpense
import logging

logger = logging.getLogger("finmind.anomaly_detector")

AMOUNT_CHANGE_THRESHOLD = Decimal("0.20")
DATE_SHIFT_THRESHOLD_DAYS = 3


def check_recurring_anomalies(user_id: int) -> list[dict]:
    alerts = []
    recurrings = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=user_id, active=True)
        .all()
    )
    for rec in recurrings:
        expenses = (
            db.session.query(Expense)
            .filter_by(user_id=user_id, source_recurring_id=rec.id)
            .order_by(Expense.spent_at.desc())
            .limit(5)
            .all()
        )
        if len(expenses) < 2:
            continue

        amounts = [e.amount for e in expenses]
        avg_amount = sum(amounts, Decimal("0")) / len(amounts)
        for e in expenses:
            if avg_amount > 0:
                change = abs(e.amount - avg_amount) / avg_amount
                if change > AMOUNT_CHANGE_THRESHOLD:
                    alert = _create_alert(
                        user_id=user_id,
                        recurring_expense_id=rec.id,
                        alert_type="amount_change",
                        severity="high" if change > Decimal("0.50") else "medium",
                        message=(
                            f"Recurring expense '{rec.notes}' amount changed "
                            f"from {avg_amount:.2f} to {e.amount:.2f} "
                            f"({change * 100:.1f}% change)"
                        ),
                    )
                    alerts.append(alert)

        dates = [e.spent_at for e in expenses]
        for i in range(len(dates) - 1):
            gap = abs((dates[i] - dates[i + 1]).days)
            expected_gap = _expected_gap_days(rec.cadence.value)
            if expected_gap and abs(gap - expected_gap) > DATE_SHIFT_THRESHOLD_DAYS:
                alert = _create_alert(
                    user_id=user_id,
                    recurring_expense_id=rec.id,
                    alert_type="date_shift",
                    severity="medium",
                    message=(
                        f"Recurring expense '{rec.notes}' date shifted: "
                        f"expected ~{expected_gap}d gap, got {gap}d gap"
                    ),
                )
                alerts.append(alert)

    missing = _check_missing_expected(user_id, recurrings)
    alerts.extend(missing)

    db.session.commit()
    return alerts


def _check_missing_expected(user_id: int, recurrings: list[RecurringExpense]) -> list[dict]:
    alerts = []
    today = date.today()
    for rec in recurrings:
        gap = _expected_gap_days(rec.cadence.value)
        if not gap:
            continue
        last_expense = (
            db.session.query(Expense)
            .filter_by(user_id=user_id, source_recurring_id=rec.id)
            .order_by(Expense.spent_at.desc())
            .first()
        )
        if last_expense:
            days_since_last = (today - last_expense.spent_at).days
            if days_since_last > gap * 2:
                alert = _create_alert(
                    user_id=user_id,
                    recurring_expense_id=rec.id,
                    alert_type="missing_expected",
                    severity="high",
                    message=(
                        f"Expected recurring expense '{rec.notes}' is missing. "
                        f"Last occurrence was {days_since_last} days ago "
                        f"(expected every ~{gap} days)"
                    ),
                )
                alerts.append(alert)
    return alerts


def _expected_gap_days(cadence: str) -> int | None:
    mapping = {"DAILY": 1, "WEEKLY": 7, "MONTHLY": 30, "YEARLY": 365}
    return mapping.get(cadence.upper())


def _create_alert(user_id: int, recurring_expense_id: int | None, alert_type: str, severity: str, message: str) -> dict:
    existing = (
        db.session.query(AnomalyAlert)
        .filter_by(
            user_id=user_id,
            recurring_expense_id=recurring_expense_id,
            alert_type=alert_type,
            acknowledged=False,
        )
        .first()
    )
    if existing:
        return _alert_to_dict(existing)

    alert = AnomalyAlert(
        user_id=user_id,
        recurring_expense_id=recurring_expense_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
    )
    db.session.add(alert)
    db.session.flush()
    logger.info("Created anomaly alert user=%s type=%s severity=%s", user_id, alert_type, severity)
    return _alert_to_dict(alert)


def _alert_to_dict(a: AnomalyAlert) -> dict:
    return {
        "id": a.id,
        "recurring_expense_id": a.recurring_expense_id,
        "alert_type": a.alert_type,
        "severity": a.severity,
        "message": a.message,
        "details": a.details,
        "acknowledged": a.acknowledged,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def list_alerts(user_id: int, include_acknowledged: bool = False) -> list[dict]:
    q = db.session.query(AnomalyAlert).filter_by(user_id=user_id)
    if not include_acknowledged:
        q = q.filter_by(acknowledged=False)
    alerts = q.order_by(AnomalyAlert.created_at.desc()).limit(100).all()
    return [_alert_to_dict(a) for a in alerts]


def acknowledge_alert(alert_id: int, user_id: int) -> bool:
    alert = db.session.query(AnomalyAlert).filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        return False
    alert.acknowledged = True
    db.session.commit()
    return True
