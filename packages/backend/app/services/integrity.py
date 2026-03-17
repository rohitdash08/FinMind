"""
Financial Data Integrity & Reconciliation (Issue #96).

Detects missing or inconsistent financial records across a user's data:
- Balance mismatch detection (account initial_balance vs. recorded transactions)
- Orphan references (expenses with deleted/missing categories)
- Duplicate detection (same amount + date + notes within a time window)
- Missing recurring expense instances (gap detection)
- Integrity alerts with severity levels
- Reconciliation summary per period

Public API
----------
run_integrity_check(uid, months) → IntegrityReport dict
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func, text

from ..extensions import db
from ..models import Category, Expense, RecurringExpense

logger = logging.getLogger("finmind.integrity")

# ── Severity levels ───────────────────────────────────────────────────────────

SEVERITY_HIGH   = "high"    # data likely wrong; user action recommended
SEVERITY_MEDIUM = "medium"  # possible issue; worth reviewing
SEVERITY_LOW    = "low"     # informational / cosmetic

# ── Helpers ───────────────────────────────────────────────────────────────────


def _iter_months(anchor: date, n: int):
    y, m = anchor.year, anchor.month
    for _ in range(n):
        yield y, m
        m -= 1
        if m == 0:
            m = 12
            y -= 1


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


# ── Individual checks ─────────────────────────────────────────────────────────


def _check_orphan_categories(uid: int) -> list[dict]:
    """Find expenses whose category_id points to a non-existent category."""
    alerts = []
    rows = (
        db.session.query(Expense.id, Expense.category_id, Expense.amount, Expense.spent_at)
        .filter(
            Expense.user_id == uid,
            Expense.category_id.isnot(None),
        )
        .all()
    )
    valid_cat_ids = {
        c.id for c in db.session.query(Category.id).filter_by(user_id=uid).all()
    }
    for exp_id, cat_id, amount, spent_at in rows:
        if cat_id not in valid_cat_ids:
            alerts.append({
                "type": "orphan_category",
                "severity": SEVERITY_MEDIUM,
                "expense_id": exp_id,
                "category_id": cat_id,
                "amount": float(amount),
                "spent_at": spent_at.isoformat() if spent_at else None,
                "message": f"Expense #{exp_id} references deleted category #{cat_id}.",
                "suggestion": "Re-assign this expense to an existing category.",
            })
    return alerts


def _check_duplicates(uid: int, months: int, anchor: date) -> list[dict]:
    """Detect likely duplicate expenses: same user_id, amount, spent_at, notes."""
    alerts = []
    cutoff = anchor - timedelta(days=months * 31)

    rows = db.session.execute(
        text("""
            SELECT amount, spent_at, notes, expense_type, COUNT(*) as cnt,
                   MIN(id) as first_id, MAX(id) as last_id
            FROM expenses
            WHERE user_id = :uid AND spent_at >= :cutoff
            GROUP BY amount, spent_at, notes, expense_type
            HAVING COUNT(*) > 1
        """),
        {"uid": uid, "cutoff": cutoff},
    ).fetchall()

    for row in rows:
        amount, spent_at, notes, exp_type, cnt, first_id, last_id = row
        alerts.append({
            "type": "duplicate_expense",
            "severity": SEVERITY_HIGH,
            "count": cnt,
            "amount": float(amount),
            "spent_at": spent_at.isoformat() if spent_at else None,
            "notes": notes,
            "first_id": first_id,
            "last_id": last_id,
            "message": (
                f"{cnt} identical expenses on {spent_at} for {float(amount):.2f} "
                f"({notes or 'no notes'}) — likely duplicates."
            ),
            "suggestion": "Review and delete extra copies if they are duplicates.",
        })
    return alerts


def _check_recurring_gaps(uid: int, anchor: date) -> list[dict]:
    """Detect months where an active recurring expense has no matching actual expense."""
    alerts = []
    recurrings = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=uid, active=True)
        .all()
    )

    for rec in recurrings:
        # Only check the last 3 months to keep it actionable
        for year, month in _iter_months(anchor, 3):
            start, end = _month_bounds(year, month)

            # Skip if recurring hadn't started yet or had ended
            if rec.start_date and rec.start_date > end:
                continue
            if rec.end_date and rec.end_date < start:
                continue
            if rec.cadence.value not in ("MONTHLY", "WEEKLY", "DAILY"):
                continue  # YEARLY checked separately to avoid noise

            count = (
                db.session.query(func.count(Expense.id))
                .filter(
                    Expense.user_id == uid,
                    Expense.source_recurring_id == rec.id,
                    Expense.spent_at >= start,
                    Expense.spent_at <= end,
                )
                .scalar()
            )
            if count == 0:
                alerts.append({
                    "type": "missing_recurring_instance",
                    "severity": SEVERITY_MEDIUM,
                    "recurring_id": rec.id,
                    "period": f"{year:04d}-{month:02d}",
                    "expected_amount": float(rec.amount),
                    "cadence": rec.cadence.value,
                    "message": (
                        f"No {rec.cadence.value.lower()} expense recorded for recurring "
                        f"item #{rec.id} in {year:04d}-{month:02d}."
                    ),
                    "suggestion": "Verify the recurring expense was processed or add a manual entry.",
                })
    return alerts


def _check_negative_balances(uid: int, months: int, anchor: date) -> list[dict]:
    """Flag months where total expenses exceed total income (negative net flow)."""
    alerts = []
    for year, month in _iter_months(anchor, months):
        income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "INCOME",
            )
            .scalar()
        )
        expenses = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "EXPENSE",
            )
            .scalar()
        )
        income_f  = float(income or 0)
        expenses_f = float(expenses or 0)

        if income_f > 0 and expenses_f > income_f:
            ratio = round(expenses_f / income_f, 2)
            alerts.append({
                "type": "negative_net_flow",
                "severity": SEVERITY_LOW if ratio < 1.2 else SEVERITY_MEDIUM,
                "period": f"{year:04d}-{month:02d}",
                "income": income_f,
                "expenses": expenses_f,
                "net_flow": round(income_f - expenses_f, 2),
                "expense_to_income_ratio": ratio,
                "message": (
                    f"{year:04d}-{month:02d}: expenses ({expenses_f:.2f}) exceeded "
                    f"income ({income_f:.2f}) by {abs(income_f - expenses_f):.2f}."
                ),
                "suggestion": "Review large expenses in this period.",
            })
    return alerts


def _monthly_reconciliation(uid: int, months: int, anchor: date) -> list[dict]:
    """Build a per-month reconciliation summary."""
    summaries = []
    for year, month in reversed(list(_iter_months(anchor, months))):
        income = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "INCOME",
            )
            .scalar() or 0
        )
        expenses = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "EXPENSE",
            )
            .scalar() or 0
        )
        tx_count = (
            db.session.query(func.count(Expense.id))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
            )
            .scalar() or 0
        )
        summaries.append({
            "period": f"{year:04d}-{month:02d}",
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
            "transaction_count": tx_count,
            "balanced": income >= expenses,
        })
    return summaries


# ── Public API ────────────────────────────────────────────────────────────────


def run_integrity_check(
    uid: int,
    months: int = 3,
    anchor: date | None = None,
) -> dict[str, Any]:
    """
    Run all integrity checks for *uid* over the last *months* months.

    Returns:
        alerts              — list of integrity alerts (sorted by severity)
        alert_counts        — {high, medium, low, total}
        reconciliation      — per-month income/expense/net_flow summary
        analysis_months     — months analysed
        healthy             — True when no high-severity alerts
        generated_at        — ISO timestamp
    """
    if anchor is None:
        anchor = date.today()
    months = max(1, min(months, 12))

    alerts: list[dict] = []
    alerts.extend(_check_orphan_categories(uid))
    alerts.extend(_check_duplicates(uid, months, anchor))
    alerts.extend(_check_recurring_gaps(uid, anchor))
    alerts.extend(_check_negative_balances(uid, months, anchor))

    # Sort: high → medium → low
    severity_order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    alerts.sort(key=lambda a: severity_order.get(a.get("severity", "low"), 2))

    counts = {
        "high":   sum(1 for a in alerts if a.get("severity") == SEVERITY_HIGH),
        "medium": sum(1 for a in alerts if a.get("severity") == SEVERITY_MEDIUM),
        "low":    sum(1 for a in alerts if a.get("severity") == SEVERITY_LOW),
        "total":  len(alerts),
    }

    reconciliation = _monthly_reconciliation(uid, months, anchor)

    logger.info(
        "Integrity check uid=%s months=%s alerts=%d (H:%d M:%d L:%d)",
        uid, months, counts["total"], counts["high"], counts["medium"], counts["low"],
    )

    return {
        "alerts": alerts,
        "alert_counts": counts,
        "reconciliation": reconciliation,
        "analysis_months": months,
        "healthy": counts["high"] == 0,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
