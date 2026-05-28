"""Tests for Natural Language Finance Query."""

import pytest


class TestNLQuery:
    def _make_txs(self):
        return [
            {"id": "1", "amount": -50, "category": "food", "date": "2024-01-15", "merchant": "pizza hut"},
            {"id": "2", "amount": -100, "category": "transport", "date": "2024-01-15", "merchant": "uber"},
            {"id": "3", "amount": -200, "category": "food", "date": "2024-01-16", "merchant": "restaurant"},
            {"id": "4", "amount": -30, "category": "coffee", "date": "2024-01-17", "merchant": "starbucks"},
            {"id": "5", "amount": -500, "category": "shopping", "date": "2024-01-20", "merchant": "amazon"},
        ]

    def test_total_query(self):
        from app.services.nl_finance_query import NLFinanceQueryService
        svc = NLFinanceQueryService()
        result = svc.execute_query("how much did I spend this month?", self._make_txs())
        assert result["result"]["value"] > 0
        assert "Total" in result["result"]["text"]

    def test_category_filter(self):
        from app.services.nl_finance_query import NLFinanceQueryService
        svc = NLFinanceQueryService()
        result = svc.execute_query("how much did I spend on food?", self._make_txs())
        assert result["matched_transactions"] == 2

    def test_parse_intent(self):
        from app.services.nl_finance_query import NLFinanceQueryService
        svc = NLFinanceQueryService()
        parsed = svc.parse_query("what is my average spending on entertainment last month?")
        assert parsed.intent == "average"
        assert parsed.category == "entertainment"

    def test_amount_filter(self):
        from app.services.nl_finance_query import NLFinanceQueryService
        svc = NLFinanceQueryService()
        parsed = svc.parse_query("show me transactions over $100")
        assert parsed.amount_filter is not None
        assert parsed.amount_filter["min"] == 100

    def test_breakdown(self):
        from app.services.nl_finance_query import NLFinanceQueryService
        svc = NLFinanceQueryService()
        result = svc.execute_query("show me a breakdown by category", self._make_txs())
        assert "breakdown" in result["result"]
