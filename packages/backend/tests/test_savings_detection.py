"""Tests for savings opportunity detection engine."""

import pytest
from datetime import date, timedelta
from app.services.savings_detection import (
    detect_opportunities,
    _detect_duplicates,
    _detect_price_increases,
    _detect_negotiable,
    _calculate_round_up,
    OpportunityType,
)


class TestDetectDuplicates:
    def test_duplicate_streaming(self):
        expenses = [
            {"amount": 15, "notes": "Netflix", "category_name": "streaming", "spent_at": str(date.today())},
            {"amount": 12, "notes": "Hulu", "category_name": "streaming", "spent_at": str(date.today())},
        ]
        results = _detect_duplicates(expenses, [])
        assert len(results) >= 1
        assert results[0]["type"] == OpportunityType.DUPLICATE_SUB

    def test_no_duplicates(self):
        expenses = [
            {"amount": 15, "notes": "Netflix", "category_name": "streaming", "spent_at": str(date.today())},
        ]
        results = _detect_duplicates(expenses, [])
        assert len(results) == 0

    def test_duplicate_from_bills(self):
        bills = [
            {"name": "Spotify Premium", "amount": 10},
            {"name": "Apple Music", "amount": 10},
        ]
        results = _detect_duplicates([], bills)
        assert len(results) >= 1


class TestDetectPriceIncrease:
    def test_price_increase(self):
        today = date.today()
        expenses = [
            {"amount": 10, "notes": "service", "category_name": "sub", "spent_at": str(today - timedelta(days=60))},
            {"amount": 15, "notes": "service", "category_name": "sub", "spent_at": str(today)},
        ]
        results = _detect_price_increases(expenses)
        assert len(results) >= 1
        assert results[0]["type"] == OpportunityType.PRICE_INCREASE

    def test_no_increase(self):
        today = date.today()
        expenses = [
            {"amount": 10, "notes": "service", "category_name": "sub", "spent_at": str(today - timedelta(days=30))},
            {"amount": 10, "notes": "service", "category_name": "sub", "spent_at": str(today)},
        ]
        results = _detect_price_increases(expenses)
        assert len(results) == 0


class TestDetectNegotiable:
    def test_negotiable_bill(self):
        bills = [{"name": "Internet Plan", "amount": 80}]
        results = _detect_negotiable(bills)
        assert len(results) == 1
        assert results[0]["type"] == OpportunityType.NEGOTIABLE

    def test_small_bill_ignored(self):
        bills = [{"name": "Internet", "amount": 5}]
        results = _detect_negotiable(bills)
        assert len(results) == 0


class TestRoundUp:
    def test_round_up(self):
        expenses = [
            {"amount": 4.50, "spent_at": str(date.today())},
            {"amount": 3.25, "spent_at": str(date.today())},
        ]
        result = _calculate_round_up(expenses)
        assert result >= 0

    def test_empty(self):
        assert _calculate_round_up([]) == 0


class TestDetectOpportunities:
    def test_full_analysis(self):
        today = date.today()
        expenses = [
            {"amount": 15, "notes": "Netflix", "category_name": "streaming", "spent_at": str(today)},
            {"amount": 12, "notes": "Hulu", "category_name": "streaming", "spent_at": str(today)},
            {"amount": 50, "notes": "groceries", "category_name": "Groceries", "spent_at": str(today)},
        ]
        bills = [{"name": "Phone Plan", "amount": 60}]
        result = detect_opportunities(expenses, bills=bills)
        assert "opportunities" in result
        assert "total_potential_monthly_savings" in result
        assert "round_up_savings_monthly" in result
        assert result["analyzed_transactions"] == 3

    def test_empty_expenses(self):
        result = detect_opportunities([])
        assert result["opportunity_count"] == 0


class TestSavingsAPI:
    def test_opportunities(self, client):
        resp = client.post("/savings/opportunities", json={
            "expenses": [
                {"amount": 15, "notes": "Netflix", "category_name": "streaming", "spent_at": str(date.today())},
                {"amount": 12, "notes": "Hulu", "category_name": "streaming", "spent_at": str(date.today())},
            ],
            "bills": [{"name": "Internet", "amount": 80}],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "opportunities" in data
        assert data["opportunity_count"] >= 1

    def test_empty_expenses(self, client):
        resp = client.post("/savings/opportunities", json={"expenses": []})
        assert resp.status_code == 400
