"""Tests for Financial Data Integrity & Reconciliation service."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

from app.services.data_integrity import (
    _check_missing_dates,
    _check_duplicates,
    _check_overdue_bills,
    _check_suspicious_amounts,
    _check_history_gaps,
    get_data_integrity_report,
)


def _make_expense(id=1, amount=100.0, date_val=None, description="Test", category_id=None):
    exp = MagicMock()
    exp.id = id
    exp.amount = amount
    exp.date = date_val or date.today()
    exp.description = description
    exp.category_id = category_id
    return exp


def _make_bill(id=1, due_date=None, status="paid"):
    bill = MagicMock()
    bill.id = id
    bill.due_date = due_date or date.today()
    bill.status = status
    bill.name = "Test Bill"
    return bill


# ──────────────────────────────────────────────
# Missing date checks
# ──────────────────────────────────────────────

def test_missing_expense_date():
    exp = _make_expense(date_val=None)
    exp.date = None
    issues = _check_missing_dates([exp], [])
    assert len(issues) == 1
    assert issues[0].issue_type == "missing_date"
    assert issues[0].severity == "error"


def test_missing_bill_date():
    bill = _make_bill(due_date=None)
    bill.due_date = None
    issues = _check_missing_dates([], [bill])
    assert len(issues) == 1
    assert issues[0].issue_type == "missing_date"


def test_no_missing_dates():
    exp = _make_expense()
    bill = _make_bill()
    issues = _check_missing_dates([exp], [bill])
    assert len(issues) == 0


# ──────────────────────────────────────────────
# Duplicate checks
# ──────────────────────────────────────────────

def test_exact_duplicate():
    today = date.today()
    exp1 = _make_expense(id=1, amount=50.0, date_val=today, description="Coffee")
    exp2 = _make_expense(id=2, amount=50.0, date_val=today, description="Coffee")
    issues = _check_duplicates([exp1, exp2])
    assert len(issues) == 1
    assert issues[0].issue_type == "duplicate"
    assert 1 in issues[0].details["expense_ids"]
    assert 2 in issues[0].details["expense_ids"]


def test_no_duplicate_different_amounts():
    today = date.today()
    exp1 = _make_expense(id=1, amount=50.0, date_val=today, description="Coffee")
    exp2 = _make_expense(id=2, amount=51.0, date_val=today, description="Coffee")
    issues = _check_duplicates([exp1, exp2])
    assert len(issues) == 0


# ──────────────────────────────────────────────
# Overdue bills
# ──────────────────────────────────────────────

def test_overdue_bill():
    past_date = date.today() - timedelta(days=5)
    bill = _make_bill(id=1, due_date=past_date, status="pending")
    issues = _check_overdue_bills([bill])
    assert len(issues) == 1
    assert issues[0].issue_type == "overdue_bill"


def test_paid_bill_not_flagged():
    past_date = date.today() - timedelta(days=5)
    bill = _make_bill(id=1, due_date=past_date, status="paid")
    issues = _check_overdue_bills([bill])
    assert len(issues) == 0


def test_future_bill_not_flagged():
    future_date = date.today() + timedelta(days=5)
    bill = _make_bill(id=1, due_date=future_date, status="pending")
    issues = _check_overdue_bills([bill])
    assert len(issues) == 0


# ──────────────────────────────────────────────
# Suspicious amounts
# ──────────────────────────────────────────────

def test_suspicious_amount_flagged():
    # Normal expenses ~$100/month, one huge outlier
    normal = [_make_expense(id=i, amount=100.0, date_val=date.today() - timedelta(days=i*30)) for i in range(1,6)]
    huge = _make_expense(id=99, amount=1500.0, date_val=date.today())  # 15x average
    issues = _check_suspicious_amounts(normal + [huge])
    flagged_ids = [i.record_id for i in issues if i.issue_type == "suspicious_amount"]
    assert 99 in flagged_ids


def test_normal_amounts_not_flagged():
    expenses = [_make_expense(id=i, amount=100.0, date_val=date.today() - timedelta(days=i*7)) for i in range(1, 8)]
    issues = _check_suspicious_amounts(expenses)
    suspicious = [i for i in issues if i.issue_type == "suspicious_amount"]
    assert len(suspicious) == 0


# ──────────────────────────────────────────────
# History gaps
# ──────────────────────────────────────────────

def test_history_gap_detected():
    # Activity in Jan, skip Feb, active in Mar
    expenses = [
        _make_expense(id=1, date_val=date(2026, 1, 15)),
        _make_expense(id=2, date_val=date(2026, 3, 10)),
    ]
    issues = _check_history_gaps(expenses, 6)
    gap_months = [i.details.get("gap_month") for i in issues if i.issue_type == "history_gap"]
    assert "2026-02" in gap_months


def test_no_gap_consecutive_months():
    expenses = [
        _make_expense(id=1, date_val=date(2026, 1, 15)),
        _make_expense(id=2, date_val=date(2026, 2, 10)),
        _make_expense(id=3, date_val=date(2026, 3, 5)),
    ]
    issues = _check_history_gaps(expenses, 6)
    gap_issues = [i for i in issues if i.issue_type == "history_gap"]
    assert len(gap_issues) == 0


# ──────────────────────────────────────────────
# Full report
# ──────────────────────────────────────────────

def test_full_report_structure():
    with patch("app.services.data_integrity.Expense") as MockExp, \
         patch("app.services.data_integrity.Bill") as MockBill, \
         patch("app.services.data_integrity.Category") as MockCat:
        MockExp.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        MockCat.query.filter_by.return_value.all.return_value = []
        result = get_data_integrity_report(1, 3)
        assert result.summary["total_issues"] == 0
        assert result.months_checked == 3
        assert isinstance(result.issues, list)