"""
Financial Data Integrity & Reconciliation service.

Detects:
- Missing date fields on expenses/bills
- Duplicate transactions (same amount + date + description)
- Orphaned category references (category_id pointing to deleted category)
- Bills with past due_date still in status=pending
- Suspicious large expenses (> 3x monthly average)
- Gaps in expense history (months with zero activity after prior activity)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime, timedelta
from collections import defaultdict

from ..models import Expense, Bill, Category


@dataclass
class IntegrityIssue:
    issue_type: str          # "missing_date", "duplicate", "orphan_category", "overdue_bill", "suspicious_amount", "history_gap"
    severity: str            # "error", "warning", "info"
    record_type: str         # "expense" or "bill"
    record_id: Optional[int]
    description: str
    details: dict = field(default_factory=dict)


@dataclass
class ReconciliationResult:
    user_id: int
    issues: list[IntegrityIssue]
    summary: dict
    months_checked: int
    checked_at: str


def _check_missing_dates(expenses: list, bills: list) -> list[IntegrityIssue]:
    issues = []
    for exp in expenses:
        if not exp.date:
            issues.append(IntegrityIssue(
                issue_type="missing_date",
                severity="error",
                record_type="expense",
                record_id=exp.id,
                description=f"Expense #{exp.id} has no date set.",
                details={"amount": float(exp.amount or 0)},
            ))
    for bill in bills:
        if not bill.due_date:
            issues.append(IntegrityIssue(
                issue_type="missing_date",
                severity="error",
                record_type="bill",
                record_id=bill.id,
                description=f"Bill #{bill.id} has no due_date set.",
                details={"name": getattr(bill, "name", "")},
            ))
    return issues


def _check_duplicates(expenses: list) -> list[IntegrityIssue]:
    """Detect exact duplicate expenses: same amount + date + description."""
    seen: dict[tuple, list[int]] = defaultdict(list)
    for exp in expenses:
        key = (float(exp.amount or 0), str(exp.date), (exp.description or "").lower().strip())
        seen[key].append(exp.id)

    issues = []
    for key, ids in seen.items():
        if len(ids) > 1:
            amount, date_str, desc = key
            issues.append(IntegrityIssue(
                issue_type="duplicate",
                severity="warning",
                record_type="expense",
                record_id=ids[0],
                description=f"Potential duplicate: {len(ids)} expenses of ${amount} on {date_str} — '{desc}'",
                details={"expense_ids": ids, "amount": amount, "date": date_str, "description": desc},
            ))
    return issues


def _check_orphan_categories(user_id: int, expenses: list) -> list[IntegrityIssue]:
    """Detect expenses referencing category_ids that no longer exist."""
    valid_category_ids = {
        c.id for c in Category.query.filter_by(user_id=user_id).all()
    }
    issues = []
    for exp in expenses:
        if exp.category_id and exp.category_id not in valid_category_ids:
            issues.append(IntegrityIssue(
                issue_type="orphan_category",
                severity="error",
                record_type="expense",
                record_id=exp.id,
                description=f"Expense #{exp.id} references category_id {exp.category_id} which no longer exists.",
                details={"category_id": exp.category_id},
            ))
    return issues


def _check_overdue_bills(bills: list) -> list[IntegrityIssue]:
    """Detect bills that are past due but not marked paid."""
    today = date.today()
    issues = []
    for bill in bills:
        if (
            hasattr(bill, "due_date")
            and bill.due_date
            and bill.due_date < today
            and getattr(bill, "status", "") != "paid"
        ):
            overdue_days = (today - bill.due_date).days
            issues.append(IntegrityIssue(
                issue_type="overdue_bill",
                severity="warning" if overdue_days <= 14 else "error",
                record_type="bill",
                record_id=bill.id,
                description=f"Bill #{bill.id} was due {bill.due_date.isoformat()} ({overdue_days}d ago) and is not paid.",
                details={
                    "due_date": bill.due_date.isoformat(),
                    "overdue_days": overdue_days,
                    "status": getattr(bill, "status", "unknown"),
                },
            ))
    return issues


def _check_suspicious_amounts(expenses: list) -> list[IntegrityIssue]:
    """Flag expenses > 3x monthly average."""
    if not expenses:
        return []

    monthly: dict[str, list[float]] = defaultdict(list)
    for exp in expenses:
        if exp.date:
            key = exp.date.strftime("%Y-%m")
            monthly[key].append(float(exp.amount or 0))

    if not monthly:
        return []

    monthly_totals = [sum(v) for v in monthly.values()]
    avg_monthly = sum(monthly_totals) / len(monthly_totals)
    if avg_monthly == 0:
        return []

    issues = []
    for exp in expenses:
        amount = float(exp.amount or 0)
        if amount > avg_monthly * 3:
            issues.append(IntegrityIssue(
                issue_type="suspicious_amount",
                severity="info",
                record_type="expense",
                record_id=exp.id,
                description=f"Expense #{exp.id} of ${amount:.2f} is {amount/avg_monthly:.1f}x the monthly average (${avg_monthly:.2f}).",
                details={"amount": amount, "monthly_average": round(avg_monthly, 2), "ratio": round(amount / avg_monthly, 2)},
            ))
    return issues


def _check_history_gaps(expenses: list, months: int) -> list[IntegrityIssue]:
    """Detect months with zero activity sandwiched between active months."""
    if not expenses:
        return []

    active_months = set()
    for exp in expenses:
        if exp.date:
            active_months.add(exp.date.strftime("%Y-%m"))

    if len(active_months) < 2:
        return []

    # Build complete range from first to last active month
    sorted_active = sorted(active_months)
    first = sorted_active[0]
    last = sorted_active[-1]

    # Generate all months in range
    issues = []
    current = datetime.strptime(first, "%Y-%m")
    end = datetime.strptime(last, "%Y-%m")
    while current < end:
        key = current.strftime("%Y-%m")
        if key not in active_months:
            issues.append(IntegrityIssue(
                issue_type="history_gap",
                severity="info",
                record_type="expense",
                record_id=None,
                description=f"No expenses recorded for {key}, but activity exists before and after.",
                details={"gap_month": key},
            ))
        # Move to next month
        next_month = current.month + 1
        next_year = current.year + (1 if next_month > 12 else 0)
        next_month = next_month if next_month <= 12 else 1
        current = current.replace(year=next_year, month=next_month)

    return issues


def get_data_integrity_report(user_id: int, months: int = 6) -> ReconciliationResult:
    """
    Run full data integrity check for a user.

    Args:
        user_id: User ID
        months: Number of months to scan (default 6)

    Returns:
        ReconciliationResult with all issues found.
    """
    months = max(1, min(24, months))
    cutoff = date.today() - timedelta(days=30 * months)

    expenses = Expense.query.filter(
        Expense.user_id == user_id,
        Expense.date >= cutoff,
    ).all()

    bills = Bill.query.filter(Bill.user_id == user_id).all()

    issues: list[IntegrityIssue] = []
    issues += _check_missing_dates(expenses, bills)
    issues += _check_duplicates(expenses)
    issues += _check_orphan_categories(user_id, expenses)
    issues += _check_overdue_bills(bills)
    issues += _check_suspicious_amounts(expenses)
    issues += _check_history_gaps(expenses, months)

    # Summary counts by severity and type
    by_severity = defaultdict(int)
    by_type = defaultdict(int)
    for issue in issues:
        by_severity[issue.severity] += 1
        by_type[issue.issue_type] += 1

    summary = {
        "total_issues": len(issues),
        "errors": by_severity.get("error", 0),
        "warnings": by_severity.get("warning", 0),
        "info": by_severity.get("info", 0),
        "by_type": dict(by_type),
        "expenses_scanned": len(expenses),
        "bills_scanned": len(bills),
    }

    return ReconciliationResult(
        user_id=user_id,
        issues=issues,
        summary=summary,
        months_checked=months,
        checked_at=datetime.utcnow().isoformat() + "Z",
    )