"""Financial data integrity & reconciliation.

Validate data consistency, detect anomalies, reconcile balances,
and generate integrity reports.
"""

import hashlib
import json
from datetime import datetime, date
from sqlalchemy import func
from ..extensions import db
from ..models import Expense


class IntegrityCheck(db.Model):
    __tablename__ = "integrity_checks"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    check_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="pass")  # pass, warn, fail
    details = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ReconciliationRecord(db.Model):
    __tablename__ = "reconciliation_records"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    expected_total = db.Column(db.Float, default=0)
    actual_total = db.Column(db.Float, default=0)
    difference = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default="balanced")  # balanced, discrepancy
    checksum = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


CHECK_TYPES = [
    "orphan_expenses",      # expenses without valid category
    "duplicate_expenses",   # potential duplicates (same amount, date, description)
    "negative_amounts",     # expenses with negative amounts
    "future_dates",         # expenses dated in the future
    "missing_descriptions", # expenses without descriptions
    "balance_checksum",     # verify running total integrity
]


def run_all_checks(user_id: int) -> list[dict]:
    results = []
    for check_type in CHECK_TYPES:
        result = run_check(user_id, check_type)
        results.append(result)
    return results


def run_check(user_id: int, check_type: str) -> dict:
    if check_type not in CHECK_TYPES:
        raise ValueError(f"Unknown check type: {check_type}")

    checkers = {
        "orphan_expenses": _check_orphans,
        "duplicate_expenses": _check_duplicates,
        "negative_amounts": _check_negatives,
        "future_dates": _check_future,
        "missing_descriptions": _check_missing_desc,
        "balance_checksum": _check_checksum,
    }

    status, details = checkers[check_type](user_id)

    record = IntegrityCheck(
        user_id=user_id, check_type=check_type,
        status=status, details=json.dumps(details),
    )
    db.session.add(record)
    db.session.commit()

    return {"id": record.id, "check_type": check_type, "status": status, "details": details}


def reconcile(user_id: int, period_start: date, period_end: date, expected_total: float) -> dict:
    actual = float(db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id,
        Expense.date >= period_start,
        Expense.date <= period_end,
    ).scalar() or 0)

    diff = round(actual - expected_total, 2)
    status = "balanced" if abs(diff) < 0.01 else "discrepancy"

    # Compute checksum of all expenses in period
    expenses = (Expense.query.filter(
        Expense.user_id == user_id,
        Expense.date >= period_start,
        Expense.date <= period_end,
    ).order_by(Expense.id).all())
    checksum = _compute_checksum(expenses)

    rec = ReconciliationRecord(
        user_id=user_id, period_start=period_start, period_end=period_end,
        expected_total=expected_total, actual_total=round(actual, 2),
        difference=diff, status=status, checksum=checksum,
    )
    db.session.add(rec)
    db.session.commit()

    return {
        "id": rec.id, "period": f"{period_start} to {period_end}",
        "expected": expected_total, "actual": round(actual, 2),
        "difference": diff, "status": status, "checksum": checksum,
    }


def get_history(user_id: int, limit: int = 20) -> list[dict]:
    checks = (IntegrityCheck.query.filter_by(user_id=user_id)
              .order_by(IntegrityCheck.created_at.desc()).limit(limit).all())
    return [
        {"id": c.id, "check_type": c.check_type, "status": c.status,
         "details": json.loads(c.details), "created_at": c.created_at.isoformat()}
        for c in checks
    ]


def get_reconciliations(user_id: int, limit: int = 10) -> list[dict]:
    recs = (ReconciliationRecord.query.filter_by(user_id=user_id)
            .order_by(ReconciliationRecord.created_at.desc()).limit(limit).all())
    return [
        {"id": r.id, "period": f"{r.period_start} to {r.period_end}",
         "expected": r.expected_total, "actual": r.actual_total,
         "difference": r.difference, "status": r.status, "checksum": r.checksum}
        for r in recs
    ]


def _check_orphans(user_id: int) -> tuple[str, dict]:
    orphans = Expense.query.filter(
        Expense.user_id == user_id, Expense.category_id.is_(None)
    ).count()
    status = "pass" if orphans == 0 else "warn"
    return status, {"orphan_count": orphans}


def _check_duplicates(user_id: int) -> tuple[str, dict]:
    dupes = (db.session.query(
        Expense.amount, Expense.date, Expense.description, func.count(Expense.id)
    ).filter(Expense.user_id == user_id)
     .group_by(Expense.amount, Expense.date, Expense.description)
     .having(func.count(Expense.id) > 1).all())
    count = len(dupes)
    status = "pass" if count == 0 else "warn"
    return status, {"duplicate_groups": count}


def _check_negatives(user_id: int) -> tuple[str, dict]:
    negs = Expense.query.filter(Expense.user_id == user_id, Expense.amount < 0).count()
    status = "pass" if negs == 0 else "fail"
    return status, {"negative_count": negs}


def _check_future(user_id: int) -> tuple[str, dict]:
    today = date.today()
    future = Expense.query.filter(Expense.user_id == user_id, Expense.date > today).count()
    status = "pass" if future == 0 else "warn"
    return status, {"future_count": future}


def _check_missing_desc(user_id: int) -> tuple[str, dict]:
    missing = Expense.query.filter(
        Expense.user_id == user_id,
        (Expense.description.is_(None)) | (Expense.description == "")
    ).count()
    status = "pass" if missing == 0 else "warn"
    return status, {"missing_count": missing}


def _check_checksum(user_id: int) -> tuple[str, dict]:
    expenses = Expense.query.filter_by(user_id=user_id).order_by(Expense.id).all()
    checksum = _compute_checksum(expenses)
    total = sum(float(e.amount) for e in expenses)
    return "pass", {"checksum": checksum, "total": round(total, 2), "count": len(expenses)}


def _compute_checksum(expenses: list) -> str:
    h = hashlib.sha256()
    for e in expenses:
        h.update(f"{e.id}:{e.amount}:{e.date}:{e.description}".encode())
    return h.hexdigest()[:16]
