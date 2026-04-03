"""Financial Data Integrity and Reconciliation service for FinMind (#96)."""
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import extract, func, and_

from ..extensions import db
from ..models import Bill, Expense, RecurringExpense, User

logger = logging.getLogger("finmind.integrity")


class IntegrityAlert:
    DUPLICATE_EXPENSE = "duplicate_expense"
    BALANCE_MISMATCH = "balance_mismatch"
    MISSING_CATEGORY = "missing_category"
    LARGE_AMOUNT = "large_amount"
    FUTURE_DATE = "future_date"
    ORPHANED_RECURRING = "orphaned_recurring"
    BILL_NEVER_PAID = "bill_never_paid"
    NEGATIVE_AMOUNT = "negative_amount"


def _get_monthly_net(uid: int, year: int, month: int) -> dict:
    """Calculate net balance for a specific month."""
    income = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.user_id == uid,
        extract("year", Expense.spent_at) == year,
        extract("month", Expense.spent_at) == month,
        Expense.expense_type == "INCOME",
    ).scalar()

    expenses = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.user_id == uid,
        extract("year", Expense.spent_at) == year,
        extract("month", Expense.spent_at) == month,
        Expense.expense_type != "INCOME",
    ).scalar()

    return {
        "income": float(income or 0),
        "expenses": float(expenses or 0),
        "net": float(income or 0) - float(expenses or 0),
    }


def check_duplicate_expenses(uid: int, threshold_hours: int = 24) -> list[dict]:
    """
    Detect potential duplicate expenses:
    - Same amount, same date, same category within threshold_hours
    """
    issues = []
    cutoff = date.today() - timedelta(days=365)

    # Get all expenses in the last year
    expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= cutoff,
        )
        .order_by(Expense.spent_at, Expense.amount)
        .all()
    )

    seen: dict[tuple, list[int]] = {}
    for exp in expenses:
        key = (float(exp.amount), str(exp.spent_at), exp.category_id)
        if key not in seen:
            seen[key] = []
        seen[key].append(exp.id)

    for key, ids in seen.items():
        if len(ids) > 1:
            issues.append({
                "type": IntegrityAlert.DUPLICATE_EXPENSE,
                "severity": "warning",
                "expense_ids": ids,
                "amount": key[0],
                "date": key[1],
                "category_id": key[2],
                "message": f"Found {len(ids)} potential duplicate expenses: amount={key[0]}, date={key[1]}",
            })

    return issues


def check_missing_categories(uid: int) -> list[dict]:
    """Find expenses with no category assigned."""
    uncategorized = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.category_id.is_(None),
            Expense.expense_type != "INCOME",
        )
        .all()
    )

    if not uncategorized:
        return []

    return [{
        "type": IntegrityAlert.MISSING_CATEGORY,
        "severity": "info",
        "expense_ids": [e.id for e in uncategorized],
        "count": len(uncategorized),
        "message": f"{len(uncategorized)} expenses have no category assigned",
    }]


def check_large_amounts(uid: int, threshold_multiplier: float = 5.0) -> list[dict]:
    """
    Detect unusually large amounts (> threshold_multiplier * average).
    """
    avg = db.session.query(
        func.avg(Expense.amount)
    ).filter(
        Expense.user_id == uid,
        Expense.expense_type != "INCOME",
    ).scalar()

    if not avg or float(avg) == 0:
        return []

    threshold = float(avg) * threshold_multiplier
    large = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.amount > threshold,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .limit(10)
        .all()
    )

    issues = []
    for exp in large:
        issues.append({
            "type": IntegrityAlert.LARGE_AMOUNT,
            "severity": "info",
            "expense_id": exp.id,
            "amount": float(exp.amount),
            "average": round(float(avg), 2),
            "threshold": round(threshold, 2),
            "date": str(exp.spent_at),
            "message": f"Expense {exp.id} amount {exp.amount} is {round(float(exp.amount)/float(avg), 1)}x above average",
        })

    return issues


def check_future_dates(uid: int) -> list[dict]:
    """Find expenses dated in the future."""
    today = date.today()
    future = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at > today,
        )
        .all()
    )

    if not future:
        return []

    return [{
        "type": IntegrityAlert.FUTURE_DATE,
        "severity": "warning",
        "expense_ids": [e.id for e in future],
        "count": len(future),
        "message": f"{len(future)} expenses have future dates (after {today})",
    }]


def check_orphaned_recurring(uid: int) -> list[dict]:
    """Find recurring expenses with expired end dates but still marked active."""
    today = date.today()
    orphaned = (
        db.session.query(RecurringExpense)
        .filter(
            RecurringExpense.user_id == uid,
            RecurringExpense.active == True,
            RecurringExpense.end_date.isnot(None),
            RecurringExpense.end_date < today,
        )
        .all()
    )

    if not orphaned:
        return []

    return [{
        "type": IntegrityAlert.ORPHANED_RECURRING,
        "severity": "warning",
        "recurring_ids": [r.id for r in orphaned],
        "count": len(orphaned),
        "message": f"{len(orphaned)} recurring expenses are past their end date but still marked active",
    }]


def check_balance_consistency(uid: int, months: int = 3) -> list[dict]:
    """
    Check if cumulative expense/income pattern is consistent month-over-month.
    Flags months where net swing is > 3x standard deviation.
    """
    today = date.today()
    monthly_nets = []
    for i in range(months + 3):  # Extra context months
        ref_date = today - timedelta(days=30 * i)
        data = _get_monthly_net(uid, ref_date.year, ref_date.month)
        monthly_nets.append(data["net"])

    if len(monthly_nets) < 3:
        return []

    avg = sum(monthly_nets) / len(monthly_nets)
    variance = sum((x - avg) ** 2 for x in monthly_nets) / len(monthly_nets)
    std = variance ** 0.5

    issues = []
    if std > 0:
        for i, net in enumerate(monthly_nets[:months]):
            ref_date = today - timedelta(days=30 * i)
            z_score = abs(net - avg) / std
            if z_score > 3.0:
                month_str = f"{ref_date.year:04d}-{ref_date.month:02d}"
                issues.append({
                    "type": IntegrityAlert.BALANCE_MISMATCH,
                    "severity": "warning",
                    "month": month_str,
                    "net": round(net, 2),
                    "average_net": round(avg, 2),
                    "z_score": round(z_score, 2),
                    "message": f"Month {month_str} net balance ({net:.2f}) is {z_score:.1f}x standard deviations from average",
                })

    return issues


def run_integrity_check(uid: int) -> dict:
    """
    Run all integrity checks and return a comprehensive report.

    Returns:
        {
            "total_issues": int,
            "alerts": [...],
            "summary": {
                "by_type": {...},
                "by_severity": {"warning": int, "info": int}
            },
            "checked_at": "2026-04-03"
        }
    """
    all_alerts = []

    checks = [
        check_duplicate_expenses(uid),
        check_missing_categories(uid),
        check_large_amounts(uid),
        check_future_dates(uid),
        check_orphaned_recurring(uid),
        check_balance_consistency(uid),
    ]

    for check_results in checks:
        all_alerts.extend(check_results)

    # Summarize
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {"warning": 0, "info": 0}
    for alert in all_alerts:
        t = alert.get("type", "unknown")
        s = alert.get("severity", "info")
        by_type[t] = by_type.get(t, 0) + 1
        by_severity[s] = by_severity.get(s, 0) + 1

    logger.info(
        "Integrity check uid=%s total_issues=%s",
        uid, len(all_alerts)
    )

    return {
        "total_issues": len(all_alerts),
        "alerts": all_alerts,
        "summary": {
            "by_type": by_type,
            "by_severity": by_severity,
        },
        "checked_at": str(date.today()),
    }


def get_reconciliation_summary(uid: int, months: int = 3) -> dict:
    """
    Generate a reconciliation summary showing monthly income/expense/net balance.
    """
    today = date.today()
    months_data = []
    for i in range(months):
        ref_date = today - timedelta(days=30 * i)
        data = _get_monthly_net(uid, ref_date.year, ref_date.month)
        months_data.append({
            "month": f"{ref_date.year:04d}-{ref_date.month:02d}",
            "income": round(data["income"], 2),
            "expenses": round(data["expenses"], 2),
            "net": round(data["net"], 2),
        })

    months_data.reverse()  # Chronological order

    total_income = sum(m["income"] for m in months_data)
    total_expenses = sum(m["expenses"] for m in months_data)
    total_net = total_income - total_expenses

    return {
        "months": months_data,
        "totals": {
            "income": round(total_income, 2),
            "expenses": round(total_expenses, 2),
            "net": round(total_net, 2),
        },
        "period_months": months,
    }

