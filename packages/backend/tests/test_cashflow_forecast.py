"""Tests for Cash-flow Forecast Engine."""

import pytest


class TestCashFlowForecast:
    def _make_txs(self, days=30, income=100, expense=50):
        from datetime import timedelta
        from datetime import date
        txs = []
        start = date(2024, 1, 1)
        for i in range(days):
            d = (start + timedelta(days=i)).isoformat()
            txs.append({"date": d, "amount": income, "type": "income"})
            txs.append({"date": d, "amount": -expense, "type": "expense"})
        return txs

    def test_basic_forecast(self):
        from app.services.cashflow_forecast import CashFlowForecastService
        svc = CashFlowForecastService()
        txs = self._make_txs(30)
        result = svc.forecast(txs, horizon_days=7, current_balance=1000)
        assert "daily_forecasts" in result
        assert len(result["daily_forecasts"]) == 7
        assert "trend" in result

    def test_positive_net(self):
        from app.services.cashflow_forecast import CashFlowForecastService
        svc = CashFlowForecastService()
        txs = self._make_txs(30, income=100, expense=50)
        result = svc.forecast(txs, horizon_days=7)
        assert result["net_change"] > 0

    def test_negative_balance_warning(self):
        from app.services.cashflow_forecast import CashFlowForecastService
        svc = CashFlowForecastService()
        txs = self._make_txs(10, income=10, expense=100)
        result = svc.forecast(txs, horizon_days=30, current_balance=100)
        assert any(w["type"] == "negative_balance" for w in result["warnings"])

    def test_recurring_detection(self):
        from app.services.cashflow_forecast import CashFlowForecastService
        svc = CashFlowForecastService()
        txs = []
        from datetime import date, timedelta
        for i in range(5):
            d = (date(2024, 1, 1) + timedelta(days=i*30)).isoformat()
            txs.append({"date": d, "amount": -1500, "type": "expense", "description": "rent"})
        recurring = svc._detect_recurring(txs, min_occurrences=3)
        assert len(recurring) > 0
        assert recurring[0]["amount"] == 1500

    def test_trend_analysis(self):
        from app.services.cashflow_forecast import CashFlowForecastService
        svc = CashFlowForecastService()
        txs = self._make_txs(30)
        daily = svc._daily_totals(txs)
        trend = svc._calculate_trend(daily)
        assert "direction" in trend
        assert "income_trend" in trend
