"""Tests for Investment Portfolio."""

import pytest


class TestPortfolio:
    def _make_service(self):
        from app.services.investment_portfolio import InvestmentPortfolioService
        return InvestmentPortfolioService()

    def test_create_portfolio(self):
        svc = self._make_service()
        p = svc.create_portfolio("Growth", "user1", initial_cash=10000)
        assert p["name"] == "Growth"
        assert p["cash_balance"] == 10000

    def test_buy_sell(self):
        svc = self._make_service()
        p = svc.create_portfolio("Test", "user1", initial_cash=10000)
        pid = p["portfolio_id"]
        svc.record_transaction(pid, "AAPL", "buy", 10, 150)
        svc.record_transaction(pid, "AAPL", "sell", 5, 180)
        val = svc.get_portfolio_value(pid, {"AAPL": 200})
        assert val["total_value"] > 10000

    def test_dividend(self):
        svc = self._make_service()
        p = svc.create_portfolio("Test", "user1", initial_cash=5000)
        pid = p["portfolio_id"]
        svc.record_transaction(pid, "MSFT", "buy", 10, 300)
        svc.record_transaction(pid, "MSFT", "dividend", 10, 0.75)
        val = svc.get_portfolio_value(pid, {"MSFT": 300})
        assert val["cash_balance"] > 5000 - 3000

    def test_allocation(self):
        svc = self._make_service()
        p = svc.create_portfolio("Test", "user1", initial_cash=10000)
        pid = p["portfolio_id"]
        svc.record_transaction(pid, "AAPL", "buy", 10, 150)
        svc.record_transaction(pid, "GOOGL", "buy", 5, 100)
        alloc = svc.get_allocation(pid, {"AAPL": 150, "GOOGL": 100})
        assert len(alloc["allocation"]) >= 2
        assert alloc["diversification_score"] > 0

    def test_performance(self):
        svc = self._make_service()
        history = [
            {"date": "2024-01-01", "value": 10000},
            {"date": "2024-02-01", "value": 10500},
            {"date": "2024-03-01", "value": 10200},
            {"date": "2024-04-01", "value": 11000},
        ]
        perf = svc.calculate_performance("any", history)
        assert perf["total_return"] > 0
        assert perf["max_drawdown"] > 0

    def test_rebalance(self):
        svc = self._make_service()
        p = svc.create_portfolio("Test", "user1", initial_cash=10000)
        pid = p["portfolio_id"]
        svc.record_transaction(pid, "AAPL", "buy", 20, 150)
        target = {"AAPL": 30, "CASH": 70}
        result = svc.suggest_rebalance(pid, target, {"AAPL": 150})
        assert len(result["suggestions"]) > 0
