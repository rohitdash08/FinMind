"""Tests for Guided Monthly Financial Review service."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from app.services.monthly_review import (
    _spending_summary,
    _bills_summary,
    _savings_progress,
    get_monthly_review,
)


def _make_expense(amount=100.0, days_ago=0):
    from datetime import timedelta
    exp = MagicMock()
    exp.amount = amount
    exp.date = date.today()
    exp.category = MagicMock()
    exp.category.name = "Food"
    return exp


def test_spending_summary_decrease():
    current = [_make_expense(80)]
    prior = [_make_expense(100)]
    section = _spending_summary(current, prior)
    assert section.score >= 70
    assert "down" in section.summary.lower() or "%" in section.summary


def test_spending_summary_increase():
    current = [_make_expense(200)]
    prior = [_make_expense(100)]
    section = _spending_summary(current, prior)
    assert section.score < 70
    assert "up" in section.summary.lower() or "increased" in section.summary.lower() or "jumped" in section.summary.lower()


def test_spending_summary_no_data():
    section = _spending_summary([], [])
    assert section.score >= 50  # neutral


def test_savings_progress_high_rate():
    # income proxy = 1200 * 1.2 = 1440, net savings = 1440 - 500 = 940 = 65%
    current = [_make_expense(500)]
    prior = [_make_expense(500)]
    section = _savings_progress(current, prior, estimated_income=1000)
    assert section.score >= 70


def test_savings_progress_zero():
    # spending equals estimated income
    current = [_make_expense(1000)]
    section = _savings_progress(current, [], estimated_income=1000)
    assert section.score <= 60


def test_bills_summary_no_bills():
    with patch("app.services.monthly_review.Bill") as MockBill:
        MockBill.query.filter.return_value.all.return_value = []
        section = _bills_summary(1, 2026, 3)
        assert section.score == 80


def test_bills_summary_all_paid():
    mock_bill = MagicMock()
    mock_bill.status = "paid"
    mock_bill.amount = 100.0
    mock_bill.due_date = date(2026, 3, 15)
    with patch("app.services.monthly_review.Bill") as MockBill:
        MockBill.query.filter.return_value.all.return_value = [mock_bill]
        section = _bills_summary(1, 2026, 3)
        assert section.score == 100


def test_bills_summary_unpaid():
    mock_bill = MagicMock()
    mock_bill.status = "pending"
    mock_bill.amount = 100.0
    mock_bill.due_date = date(2026, 3, 15)
    with patch("app.services.monthly_review.Bill") as MockBill:
        MockBill.query.filter.return_value.all.return_value = [mock_bill]
        section = _bills_summary(1, 2026, 3)
        assert section.score < 80
        assert section.data["pending"] == 1


def test_get_monthly_review_structure():
    with patch("app.services.monthly_review.Expense") as MockExp, \
         patch("app.services.monthly_review.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = get_monthly_review(1, 2026, 3)
        assert result.review_month == "2026-03"
        assert 0 <= result.overall_score <= 100
        assert result.grade in ("A", "B", "C", "D", "F")
        assert len(result.sections) == 4
        assert len(result.action_items) > 0


def test_get_monthly_review_january_edge_case():
    """January should pull prior year December as comparison month."""
    with patch("app.services.monthly_review.Expense") as MockExp, \
         patch("app.services.monthly_review.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = get_monthly_review(1, 2026, 1)  # January
        assert result.review_month == "2026-01"