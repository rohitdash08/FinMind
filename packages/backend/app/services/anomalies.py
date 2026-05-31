import calendar
from datetime import datetime, timedelta, date
from ..extensions import db
from ..models import AnomalyAlert, RecurringExpense, Expense
import logging

logger = logging.getLogger("finmind.anomalies")


def _advance_date(at: date, cadence: str) -> date:
    if cadence == "DAILY":
        return at + timedelta(days=1)
    if cadence == "WEEKLY":
        return at + timedelta(days=7)
    if cadence == "MONTHLY":
        year = at.year + (1 if at.month == 12 else 0)
        month = 1 if at.month == 12 else at.month + 1
        day = min(at.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    year = at.year + 1
    day = min(at.day, calendar.monthrange(year, at.month)[1])
    return date(year, at.month, day)


def check_recurring_anomalies(uid: int) -> list[dict]:
    alerts = []
    recurrings = (
        db.session.query(RecurringExpense).filter_by(user_id=uid, active=True).all()
    )
    for rec in recurrings:
        alert = _check_single_recurring(uid, rec)
        if alert:
            alerts.append(alert)
    logger.info("Checked anomalies user=%s alerts=%s", uid, len(alerts))
    return alerts


def _check_single_recurring(uid: int, rec: RecurringExpense) -> dict | None:
    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=uid, source_recurring_id=rec.id)
        .order_by(Expense.spent_at.desc())
        .limit(3)
        .all()
    )
    if len(expenses) < 2:
        return None

    amounts = [float(e.amount) for e in expenses]
    avg_amount = sum(amounts) / len(amounts)
    latest = expenses[0]

    if abs(float(latest.amount) - avg_amount) / max(avg_amount, 1) > 0.2:
        alert = _create_alert(
            uid, rec.id, "amount_change",
            f"Amount changed from avg {avg_amount:.2f} to {float(latest.amount):.2f} for {rec.notes}",
            "warning",
        )
        return _alert_to_dict(alert)

    expected = _advance_date(latest.spent_at, rec.cadence.value)
    if (datetime.utcnow().date() - expected).days > 7:
        alert = _create_alert(
            uid, rec.id, "missing",
            f"Expected transaction for {rec.notes} around {expected.isoformat()}",
            "info",
        )
        return _alert_to_dict(alert)

    return None


def _create_alert(
    uid: int, recurring_id: int, alert_type: str, description: str, severity: str
) -> AnomalyAlert:
    alert = AnomalyAlert(
        user_id=uid,
        recurring_id=recurring_id,
        alert_type=alert_type,
        description=description,
        severity=severity,
    )
    db.session.add(alert)
    db.session.commit()
    return alert


def _alert_to_dict(a: AnomalyAlert) -> dict:
    return {
        "id": a.id,
        "recurring_id": a.recurring_id,
        "alert_type": a.alert_type,
        "description": a.description,
        "severity": a.severity,
        "dismissed": a.dismissed,
        "created_at": a.created_at.isoformat(),
    }


def list_alerts(uid: int) -> list[AnomalyAlert]:
    return (
        db.session.query(AnomalyAlert)
        .filter_by(user_id=uid)
        .order_by(AnomalyAlert.created_at.desc())
        .all()
    )


def dismiss_alert(uid: int, alert_id: int) -> bool:
    alert = db.session.get(AnomalyAlert, alert_id)
    if not alert or alert.user_id != uid:
        return False
    alert.dismissed = True
    db.session.commit()
    return True
