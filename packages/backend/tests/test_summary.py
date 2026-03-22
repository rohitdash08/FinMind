"""
tests/test_summary.py — Unit tests for Smart Weekly Digest
Issue #121 · rohitdash08/FinMind
Author: Xavier Abraham Sandoval <abrahamsandoval.as@gmail.com>
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.routes.summary import (
    _aggregate_week,
    _category_breakdown,
    _daily_trend,
    _generate_insights,
    _week_bounds,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_row(**kwargs):
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# ── _week_bounds ───────────────────────────────────────────────────────────────

class TestWeekBounds:
    def test_returns_monday_to_sunday(self):
        start, end = _week_bounds(offset=0)
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6    # Sunday
        assert (end - start).days == 6

    def test_offset_goes_back(self):
        curr_start, _ = _week_bounds(offset=0)
        prev_start, _ = _week_bounds(offset=1)
        assert curr_start - prev_start == timedelta(weeks=1)


# ── _generate_insights ─────────────────────────────────────────────────────────

class TestGenerateInsights:
    def _curr(self, expenses=100.0, income=200.0):
        return {"total_expenses": expenses, "total_income": income, "net": income - expenses}

    def _prev(self, expenses=80.0, income=150.0):
        return {"total_expenses": expenses, "total_income": income, "net": income - expenses}

    def test_spending_increased(self):
        insights = _generate_insights(self._curr(expenses=100), self._prev(expenses=80))
        assert any("increased" in i for i in insights)

    def test_spending_decreased(self):
        insights = _generate_insights(self._curr(expenses=60), self._prev(expenses=80))
        assert any("decreased" in i for i in insights)

    def test_positive_cashflow(self):
        insights = _generate_insights(self._curr(expenses=100, income=200), self._prev())
        assert any("Positive" in i for i in insights)

    def test_negative_cashflow(self):
        insights = _generate_insights(self._curr(expenses=300, income=100), self._prev())
        assert any("Negative" in i for i in insights)

    def test_first_week_no_previous(self):
        insights = _generate_insights(self._curr(expenses=50), self._prev(expenses=0))
        assert any("First week" in i for i in insights)


# ── _aggregate_week ────────────────────────────────────────────────────────────

class TestAggregateWeek:
    @patch("app.routes.summary.db")
    def test_aggregation_structure(self, mock_db):
        mock_rows = [
            _make_row(expense_type="EXPENSE", total=Decimal("150.00"), count=5),
            _make_row(expense_type="INCOME", total=Decimal("500.00"), count=2),
        ]
        mock_db.session.query.return_value.filter.return_value.group_by.return_value.all.return_value = mock_rows

        result = _aggregate_week(1, date.today(), date.today())

        assert result["total_expenses"] == pytest.approx(150.0)
        assert result["total_income"] == pytest.approx(500.0)
        assert result["net"] == pytest.approx(350.0)
        assert result["expense_count"] == 5
        assert result["income_count"] == 2

    @patch("app.routes.summary.db")
    def test_empty_week(self, mock_db):
        mock_db.session.query.return_value.filter.return_value.group_by.return_value.all.return_value = []
        result = _aggregate_week(1, date.today(), date.today())
        assert result["total_expenses"] == 0.0
        assert result["net"] == 0.0


# ── _daily_trend ───────────────────────────────────────────────────────────────

class TestDailyTrend:
    @patch("app.routes.summary.db")
    def test_fills_all_days(self, mock_db):
        start = date(2026, 3, 16)  # Monday
        end = date(2026, 3, 22)    # Sunday
        mock_db.session.query.return_value.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = []

        trend = _daily_trend(1, start, end)

        assert len(trend) == 7
        assert all(t["amount"] == 0.0 for t in trend)
        assert trend[0]["date"] == "2026-03-16"
        assert trend[-1]["date"] == "2026-03-22"
