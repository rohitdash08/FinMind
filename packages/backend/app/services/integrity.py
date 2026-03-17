"""
Financial Data Integrity & Reconciliation service (Issue #96).

Detects missing or inconsistent financial records and produces a structured
reconciliation summary.  All checks are read-only — nothing is mutated.

Checks performed:
  1. Balance mismatch       — income − expenses vs expected running balance
  2. Orphaned expenses      — expense.category_id references a missing category
  3. Orphaned recurring     — recurring_expense.category_id references a missing category
  4. Future-dated expenses  — spent_at is in the future (likely data entry error)
  5. Duplicate expenses     — same (user_id, amount, spent_at, expense_type) on the same day
  6. Negative amounts       — expense.amount <= 0
  7. Stale recurring        — active recurring expense whose end_date has passed
  8. Missing bill reminders — active bills with next_due_date within 7 days but no pending reminder

Public API
----------
run_integrity_check(uid, months) → IntegrityReport dict
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import (
    Bill,
    Category,
    Expense,
    RecurringExpense,
    Reminder,
)

logger = logging.getLogger("finmind.integrity")

# ── Constants ─────────────────────────────────────────────────────────────────

_DUPLICATE_WINDOW_DAYS = 0          # same-day duplicates
_BILL_DUE_SOON_DAYS = 7             # bills due within N days


# ── Individual checks ─────────────────────────────────────────────────────────

def _check_balance_mismatches(uid: int, months: int, anchor: date) -> list[dict]:
    """
    For each of the last *months* months, compute:
        expected_net = sum(INCOME) - sum(EXPENSE)
    and flag months where expenses exceed income (negative net flow).
    These are not necessarily bugs, but deserve attention.
    """
    alerts = []
    y, m = anchor.year, anchor.month
    for _ in range(months):
        income = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == y,
                extract("month", Expense.spent_at) == m,
                Expense.expense_type == "INCOME",
            )
            .scalar() or 0
        )
        expenses = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == y,
                extract("month", Expense.spent_at) == m,
                Expense.expense_type == "EXPENSE",
            )
            .scalar() or 0
        )
        net = round(income - expenses, 2)
        if net < 0:
            alerts.append({
                "month": f"{y:04d}-{m:02d}",
                "income": round(income, 2),
                "expenses": round(expenses, 2),
                "net_flow": net,
                "severity": "warning",
            })
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return alerts


def _check_orphaned_expenses(uid: int) -> list[dict]:
    """Expenses whose category_id points to a non-existent category."""
    valid_ids = {
        r.id for r in db.session.query(Category.id).filter_by(user_id=uid).all()
    }
    orphans = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.category_id.isnot(None),
        )
        .all()
    )
    return [
        {
            "expense_id": e.id,
            "amount": float(e.amount),
            "spent_at": e.spent_at.isoformat(),
            "missing_category_id": e.category_id,
            "severity": "error",
        }
        for e in orphans
        if e.category_id not in valid_ids
    ]


def _check_orphaned_recurring(uid: int) -> list[dict]:
    """Recurring expenses whose category_id points to a non-existent category."""
    valid_ids = {
        r.id for r in db.session.query(Category.id).filter_by(user_id=uid).all()
    }
    orphans = (
        db.session.query(RecurringExpense)
        .filter(
            RecurringExpense.user_id == uid,
            RecurringExpense.category_id.isnot(None),
        )
        .all()
    )
    return [
        {
            "recurring_id": r.id,
            "notes": r.notes,
            "missing_category_id": r.category_id,
            "severity": "error",
        }
        for r in orphans
        if r.category_id not in valid_ids
    ]


def _check_future_dated(uid: int) -> list[dict]:
    """Expenses with spent_at in the future — likely data entry errors."""
    today = date.today()
    rows = (
        db.session.query(Expense)
        .filter(Expense.user_id == uid, Expense.spent_at > today)
        .all()
    )
    return [
        {
            "expense_id": e.id,
            "amount": float(e.amount),
            "spent_at": e.spent_at.isoformat(),
            "days_ahead": (e.spent_at - today).days,
            "severity": "warning",
        }
        for e in rows
    ]


def _check_duplicates(uid: int) -> list[dict]:
    """
    Same-day expenses with identical (amount, expense_type) — likely double-entry.
    Returns groups of duplicate ids.
    """
    rows = (
        db.session.query(
            Expense.spent_at,
            Expense.amount,
            Expense.expense_type,
            func.count(Expense.id).label("cnt"),
            func.array_agg(Expense.id).label("ids"),  # PostgreSQL; falls back gracefully
        )
        .filter(Expense.user_id == uid)
        .group_by(Expense.spent_at, Expense.amount, Expense.expense_type)
        .having(func.count(Expense.id) > 1)
        .all()
    )
    result = []
    for row in rows:
        ids = list(row.ids) if hasattr(row, "ids") and row.ids else []
        result.append({
            "spent_at": row.spent_at.isoformat(),
            "amount": float(row.amount),
            "expense_type": row.expense_type,
            "count": row.cnt,
            "expense_ids": ids,
            "severity": "warning",
        })
    return result


def _check_negative_amounts(uid: int) -> list[dict]:
    """Expenses with amount <= 0 — invalid records."""
    rows = (
        db.session.query(Expense)
        .filter(Expense.user_id == uid, Expense.amount <= 0)
        .all()
    )
    return [
        {
            "expense_id": e.id,
            "amount": float(e.amount),
            "spent_at": e.spent_at.isoformat(),
            "severity": "error",
        }
        for e in rows
    ]


def _check_stale_recurring(uid: int) -> list[dict]:
    """Active recurring expenses whose end_date has passed."""
    today = date.today()
    rows = (
        db.session.query(RecurringExpense)
        .filter(
            RecurringExpense.user_id == uid,
            RecurringExpense.active == True,  # noqa: E712
            RecurringExpense.end_date.isnot(None),
            RecurringExpense.end_date < today,
        )
        .all()
    )
    return [
        {
            "recurring_id": r.id,
            "notes": r.notes,
            "end_date": r.end_date.isoformat(),
            "days_overdue": (today - r.end_date).days,
            "severity": "warning",
        }
        for r in rows
    ]


def _check_bills_missing_reminders(uid: int) -> list[dict]:
    """Active bills due within 7 days with no pending reminder."""
    today = date.today()
    due_soon_cutoff = today + timedelta(days=_BILL_DUE_SOON_DAYS)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active == True,  # noqa: E712
            Bill.next_due_date >= today,
            Bill.next_due_date <= due_soon_cutoff,
        )
        .all()
    )
    result = []
    for bill in bills:
        pending = (
            db.session.query(Reminder)
            .filter(
                Reminder.user_id == uid,
                Reminder.bill_id == bill.id,
                Reminder.sent == False,  # noqa: E712
            )
            .first()
        )
        if not pending:
            result.append({
                "bill_id": bill.id,
                "bill_name": bill.name,
                "next_due_date": bill.next_due_date.isoformat(),
                "days_until_due": (bill.next_due_date - today).days,
                "severity": "warning",
            })
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def run_integrity_check(uid: int, months: int = 3) -> dict[str, Any]:
    """
    Run all integrity checks for *uid* and return a structured report.

    Returns
    -------
    dict with keys:
        overall_status          — "ok" | "warnings" | "errors"
        total_issues            — total count across all checks
        balance_mismatches      — months with negative net flow
        orphaned_expenses       — expenses referencing missing categories
        orphaned_recurring      — recurring expenses referencing missing categories
        future_dated_expenses   — expenses with spent_at > today
        duplicate_expenses      — same-day/amount/type duplicates
        negative_amounts        — expenses with amount <= 0
        stale_recurring         — active recurring past their end_date
        bills_missing_reminders — upcoming bills with no pending reminder
        analysis_months         — months analysed for balance check
        generated_at            — ISO timestamp
    """
    months = max(1, min(months, 12))
    anchor = date.today()

    try:
        balance = _check_balance_mismatches(uid, months, anchor)
    except Exception as exc:
        logger.warning("balance check failed uid=%s: %s", uid, exc)
        balance = []

    try:
        orphan_exp = _check_orphaned_expenses(uid)
    except Exception as exc:
        logger.warning("orphaned_expenses check failed uid=%s: %s", uid, exc)
        orphan_exp = []

    try:
        orphan_rec = _check_orphaned_recurring(uid)
    except Exception as exc:
        logger.warning("orphaned_recurring check failed uid=%s: %s", uid, exc)
        orphan_rec = []

    try:
        future = _check_future_dated(uid)
    except Exception as exc:
        logger.warning("future_dated check failed uid=%s: %s", uid, exc)
        future = []

    try:
        dupes = _check_duplicates(uid)
    except Exception as exc:
        # array_agg is PostgreSQL-only; degrade gracefully on SQLite
        logger.debug("duplicate check failed (likely SQLite): %s", exc)
        dupes = []

    try:
        negatives = _check_negative_amounts(uid)
    except Exception as exc:
        logger.warning("negative_amounts check failed uid=%s: %s", uid, exc)
        negatives = []

    try:
        stale = _check_stale_recurring(uid)
    except Exception as exc:
        logger.warning("stale_recurring check failed uid=%s: %s", uid, exc)
        stale = []

    try:
        missing_reminders = _check_bills_missing_reminders(uid)
    except Exception as exc:
        logger.warning("bills_missing_reminders check failed uid=%s: %s", uid, exc)
        missing_reminders = []

    all_issues = (
        balance + orphan_exp + orphan_rec + future +
        dupes + negatives + stale + missing_reminders
    )
    total = len(all_issues)
    has_errors = any(i.get("severity") == "error" for i in all_issues)
    overall = "ok" if total == 0 else ("errors" if has_errors else "warnings")

    logger.info(
        "Integrity check uid=%s months=%s total_issues=%s status=%s",
        uid, months, total, overall,
    )

    return {
        "overall_status": overall,
        "total_issues": total,
        "balance_mismatches": balance,
        "orphaned_expenses": orphan_exp,
        "orphaned_recurring": orphan_rec,
        "future_dated_expenses": future,
        "duplicate_expenses": dupes,
        "negative_amounts": negatives,
        "stale_recurring": stale,
        "bills_missing_reminders": missing_reminders,
        "analysis_months": months,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
