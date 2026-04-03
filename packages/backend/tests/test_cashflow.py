"""Tests for advanced cash flow forecasting (#93)."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, PropertyMock
from packages.backend.app.services.cashflow import (
    _days_in_month,
    _next_month,
    _add_months,
    _calculate_trend,
    _confidence_from_data_points,
    forecast_cash_flow,
)


class TestDateHelpers:
    def test_days_in_month_january(self):
        assert _days_in_month(2026, 1) == 31

    def test_days_in_month_february_leap(self):
        assert _days_in_month(2024, 2) == 29

    def test_days_in_month_february_non_leap(self):
        assert _days_in_month(2025, 2) == 28

    def test_days_in_month_april(self):
        assert _days_in_month(2026, 4) == 30

    def test_next_month_normal(self):
        assert _next_month(2026, 3) == (2026, 4)

    def test_next_month_december(self):
        assert _next_month(2026, 12) == (2027, 1)

    def test_add_months_simple(self):
        d = date(2026, 3, 15)
        result = _add_months(d, 1)
        assert result == date(2026, 4, 15)

    def test_add_months_year_boundary(self):
        d = date(2026, 11, 15)
        result = _add_months(d, 3)
        assert result == date(2027, 2, 15)

    def test_add_months_clamps_day(self):
        d = date(2026, 1, 31)
        result = _add_months(d, 1)
        assert result == date(2026, 2, 28)


class TestTrendCalculation:
    def test_rising_trend_positive_slope(self):
        values = [1000, 1100, 1200, 1300, 1400]
        slope = _calculate_trend(values)
        assert slope > 0

    def test_declining_trend_negative_slope(self):
        values = [2000, 1800, 1600, 1400, 1200]
        slope = _calculate_trend(values)
        assert slope < 0

    def test_flat_trend_near_zero(self):
        values = [1000, 1000, 1000, 1000]
        slope = _calculate_trend(values)
        assert abs(slope) < 1

    def test_single_value_returns_zero(self):
        assert _calculate_trend([5000]) == 0.0

    def test_empty_list_returns_zero(self):
        assert _calculate_trend([]) == 0.0


class TestConfidenceLabels:
    def test_high_confidence_with_6_months(self):
        assert _confidence_from_data_points(6) == "high"

    def test_high_confidence_with_more_than_6(self):
        assert _confidence_from_data_points(10) == "high"

    def test_medium_confidence_with_3_to_5_months(self):
        assert _confidence_from_data_points(3) == "medium"
        assert _confidence_from_data_points(5) == "medium"

    def test_low_confidence_with_fewer_than_3(self):
        assert _confidence_from_data_points(1) == "low"
        assert _confidence_from_data_points(2) == "low"


class TestForecastCashFlow:
    def _make_db_mock(self, historical_data=None, recurring=None, bills=None):
        """Create mock db with configurable return values."""
        mock_db = MagicMock()
        call_count = [0]

        income_values = [h["income"] for h in (historical_data or [])]
        expense_values = [h["expenses"] for h in (historical_data or [])]
        query_results = []
        for i in range(len(income_values)):
            query_results.extend([income_values[i], expense_values[i]])

        def scalar_side(*a, **kw):
            if query_results:
                return query_results.pop(0)
            return 0

        mock_scalar_q = MagicMock()
        mock_scalar_q.filter.return_value = mock_scalar_q
        mock_scalar_q.scalar.side_effect = scalar_side

        mock_rec_q = MagicMock()
        mock_rec_q.filter.return_value = mock_rec_q
        mock_rec_q.all.return_value = recurring or []

        mock_bills_q = MagicMock()
        mock_bills_q.filter.return_value = mock_bills_q
        mock_bills_q.all.return_value = bills or []

        def query_dispatch(model):
            from packages.backend.app.models import Expense, RecurringExpense, Bill
            if model is RecurringExpense:
                return mock_rec_q
            elif model is Bill:
                return mock_bills_q
            return mock_scalar_q

        mock_db.session.query.side_effect = query_dispatch
        return mock_db

    def test_forecast_returns_correct_structure(self):
        with patch("packages.backend.app.services.cashflow.db") as mock_db:
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.scalar.return_value = 0
            mock_q.all.return_value = []
            mock_db.session.query.return_value = mock_q

            result = forecast_cash_flow(1, 3)

        assert "months" in result
        assert "summary" in result
        assert len(result["months"]) == 3

    def test_each_month_has_required_fields(self):
        with patch("packages.backend.app.services.cashflow.db") as mock_db:
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.scalar.return_value = 0
            mock_q.all.return_value = []
            mock_db.session.query.return_value = mock_q

            result = forecast_cash_flow(1, 2)

        for month in result["months"]:
            assert "month" in month
            assert "projected_income" in month
            assert "projected_expenses" in month
            assert "projected_net" in month
            assert "scheduled_recurring" in month
            assert "scheduled_bills" in month
            assert "confidence" in month
            assert "anomaly" in month

    def test_months_capped_at_12(self):
        with patch("packages.backend.app.services.cashflow.db") as mock_db:
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.scalar.return_value = 0
            mock_q.all.return_value = []
            mock_db.session.query.return_value = mock_q

            result = forecast_cash_flow(1, 99)

        assert len(result["months"]) == 12

    def test_months_minimum_1(self):
        with patch("packages.backend.app.services.cashflow.db") as mock_db:
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.scalar.return_value = 0
            mock_q.all.return_value = []
            mock_db.session.query.return_value = mock_q

            result = forecast_cash_flow(1, 0)

        assert len(result["months"]) == 1

    def test_projected_net_equals_income_minus_expenses(self):
        with patch("packages.backend.app.services.cashflow.db") as mock_db:
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.scalar.return_value = 50000
            mock_q.all.return_value = []
            mock_db.session.query.return_value = mock_q

            result = forecast_cash_flow(1, 1)

        month = result["months"][0]
        expected_net = round(month["projected_income"] - month["projected_expenses"], 2)
        assert month["projected_net"] == expected_net

    def test_improving_trend_detected(self):
        """When net income is rising, trend should be improving."""
        with patch("packages.backend.app.services.cashflow.db") as mock_db:
            with patch("packages.backend.app.services.cashflow._get_monthly_actual") as mock_actual:
                # Progressively improving months
                mock_actual.side_effect = [
                    {"income": 40000, "expenses": 35000},
                    {"income": 42000, "expenses": 34000},
                    {"income": 44000, "expenses": 33000},
                    {"income": 46000, "expenses": 32000},
                    {"income": 48000, "expenses": 31000},
                    {"income": 50000, "expenses": 30000},
                ]
                with patch("packages.backend.app.services.cashflow._get_recurring_monthly", return_value=0):
                    with patch("packages.backend.app.services.cashflow._get_upcoming_bills", return_value=0):
                        result = forecast_cash_flow(1, 3)

        assert result["summary"]["trend"] == "improving"

    def test_anomaly_flagged_when_large_deficit(self):
        """When projected expenses >> income, anomaly should be True."""
        with patch("packages.backend.app.services.cashflow.db") as mock_db:
            with patch("packages.backend.app.services.cashflow._get_monthly_actual") as mock_actual:
                mock_actual.side_effect = [
                    {"income": 50000, "expenses": 20000},
                ] * 6
                # Huge bills upcoming
                with patch("packages.backend.app.services.cashflow._get_recurring_monthly", return_value=0):
                    with patch("packages.backend.app.services.cashflow._get_upcoming_bills", return_value=80000):
                        result = forecast_cash_flow(1, 1)

        assert result["months"][0]["anomaly"] is True

    def test_summary_contains_correct_fields(self):
        with patch("packages.backend.app.services.cashflow.db") as mock_db:
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.scalar.return_value = 0
            mock_q.all.return_value = []
            mock_db.session.query.return_value = mock_q

            result = forecast_cash_flow(1, 3)

        assert "avg_monthly_surplus" in result["summary"]
        assert "trend" in result["summary"]
        assert "data_quality" in result["summary"]
        assert "historical_months_used" in result["summary"]
        assert result["summary"]["trend"] in ("improving", "declining", "stable")
        assert result["summary"]["data_quality"] in ("high", "medium", "low")

