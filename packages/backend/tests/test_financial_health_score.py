"""Tests for Predictive Financial Health Score service."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

from app.services.financial_health_score import (
    _grade,
    _summary,
    _savings_score,
    _stability_score,
    _trend_score,
    get_financial_health_score,
    WEIGHT_SAVINGS,
    WEIGHT_STABILITY,
    WEIGHT_BILL_RELIABILITY,
    WEIGHT_TREND,
)


# ──────────────────────────────────────────────
# Grade and summary helpers
# ──────────────────────────────────────────────

def test_grade_a():
    assert _grade(90) == "A"

def test_grade_b():
    assert _grade(72) == "B"

def test_grade_c():
    assert _grade(60) == "C"

def test_grade_d():
    assert _grade(42) == "D"

def test_grade_f():
    assert _grade(35) == "F"

def test_summary_excellent():
    assert "Excellent" in _summary(90)

def test_summary_poor():
    assert "Poor" in _summary(30)


# ──────────────────────────────────────────────
# _savings_score
# ──────────────────────────────────────────────

def _make_expense(amount, days_ago=0):
    exp = MagicMock()
    exp.amount = amount
    exp.date = date.today() - timedelta(days=days_ago)
    return exp


def test_savings_score_no_expenses():
    score, explanation = _savings_score([], 6)
    assert score == 50.0
    assert "Not enough" in explanation


def test_savings_score_high_savings():
    # Spending always much less than max (low avg/max ratio)
    expenses = []
    today = date.today()
    for month_offset in range(6):
        days_ago = month_offset * 30
        expenses.append(_make_expense(100, days_ago))
    score, explanation = _savings_score(expenses, 6)
    assert score >= 50  # Should get decent score


def test_savings_score_max_spending():
    # Every month spends equally (avg=max, ratio=1)
    expenses = []
    for month_offset in range(6):
        days_ago = month_offset * 30
        expenses.append(_make_expense(500, days_ago))
    score, _ = _savings_score(expenses, 6)
    assert score <= 70  # Not a great savings score


# ──────────────────────────────────────────────
# _stability_score
# ──────────────────────────────────────────────

def test_stability_score_no_data():
    score, explanation = _stability_score([], 6)
    assert score == 50.0

def test_stability_score_perfect_stability():
    # Same spending every month
    expenses = []
    for month_offset in range(6):
        days_ago = month_offset * 30
        expenses.append(_make_expense(300, days_ago))
    score, explanation = _stability_score(expenses, 6)
    assert score >= 90  # Very stable
    assert "stable" in explanation.lower()


def test_stability_score_high_volatility():
    # Wildly different spending each month
    expenses = [
        _make_expense(100, 0),    # this month
        _make_expense(5000, 30),  # last month huge spike
        _make_expense(100, 60),
        _make_expense(4000, 90),
        _make_expense(100, 120),
        _make_expense(5000, 150),
    ]
    score, explanation = _stability_score(expenses, 6)
    assert score < 50


# ──────────────────────────────────────────────
# _trend_score
# ──────────────────────────────────────────────

def test_trend_score_not_enough_data():
    expenses = [_make_expense(100, 0)]
    score, explanation = _trend_score(expenses)
    assert score == 50.0

def test_trend_score_improving():
    # Recent months spending LESS than prior months -> positive trend
    expenses = []
    for i in range(3):
        expenses.append(_make_expense(800, i * 30))    # recent: 800/mo
    for i in range(3, 6):
        expenses.append(_make_expense(1200, i * 30))   # prior: 1200/mo
    score, explanation = _trend_score(expenses)
    assert score > 50
    assert "Positive" in explanation or "decreased" in explanation


def test_trend_score_worsening():
    # Recent months spending MORE than prior -> negative trend
    expenses = []
    for i in range(3):
        expenses.append(_make_expense(1500, i * 30))   # recent: high
    for i in range(3, 6):
        expenses.append(_make_expense(500, i * 30))    # prior: low
    score, explanation = _trend_score(expenses)
    assert score < 50


# ──────────────────────────────────────────────
# Weights sum to 1.0
# ──────────────────────────────────────────────

def test_weights_sum():
    total = WEIGHT_SAVINGS + WEIGHT_STABILITY + WEIGHT_BILL_RELIABILITY + WEIGHT_TREND
    assert abs(total - 1.0) < 0.001


# ──────────────────────────────────────────────
# get_financial_health_score (integration)
# ──────────────────────────────────────────────

def test_full_score_range():
    """Score should always be 0-100."""
    with patch("app.services.financial_health_score.Expense") as MockExpense, \
         patch("app.services.financial_health_score.Bill") as MockBill:
        MockExpense.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.count.return_value = 0
        result = get_financial_health_score(1, 3)
        assert 0 <= result.overall_score <= 100


def test_full_score_has_dimensions():
    with patch("app.services.financial_health_score.Expense") as MockExpense, \
         patch("app.services.financial_health_score.Bill") as MockBill:
        MockExpense.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.count.return_value = 0
        result = get_financial_health_score(1, 3)
        assert len(result.dimensions) == 4
        names = {d.name for d in result.dimensions}
        assert "savings_strength" in names
        assert "spending_stability" in names
        assert "bill_reliability" in names
        assert "trend_direction" in names


def test_full_score_months_clamped():
    with patch("app.services.financial_health_score.Expense") as MockExpense, \
         patch("app.services.financial_health_score.Bill") as MockBill:
        MockExpense.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.count.return_value = 0
        result = get_financial_health_score(1, 100)  # over max
        assert result.months_analyzed == 24