"""
Tests for explainable spending insights.
"""

import pytest
from app.services.explainable import generate_insights, get_spending_summary


class TestCategoryInsights:
    def test_new_category(self, app, db_session):
        with app.app_context():
            insights = generate_insights(
                current=[{"category": "travel", "amount": 500, "merchant": "Airbnb"}],
                previous=[],
            )
            assert any("New spending in travel" in i.what_changed for i in insights)

    def test_stopped_category(self, app, db_session):
        with app.app_context():
            insights = generate_insights(
                current=[],
                previous=[{"category": "entertainment", "amount": 200, "merchant": "Cinema"}],
            )
            assert any("Stopped" in i.what_changed for i in insights)

    def test_increase_frequency(self, app, db_session):
        with app.app_context():
            prev = [{"category": "food", "amount": 15, "merchant": "Subway"}] * 3
            curr = [{"category": "food", "amount": 15, "merchant": "Subway"}] * 8
            insights = generate_insights(curr, prev)
            food_insights = [i for i in insights if i.category == "food"]
            assert any("frequent" in i.why.lower() for i in food_insights)

    def test_high_confidence(self, app, db_session):
        with app.app_context():
            prev = [{"category": "food", "amount": 10}] * 5
            curr = [{"category": "food", "amount": 20}] * 5
            insights = generate_insights(curr, prev)
            food = [i for i in insights if i.category == "food"]
            assert any(i.confidence == "high" for i in food)


class TestMerchantInsights:
    def test_new_merchant(self, app, db_session):
        with app.app_context():
            insights = generate_insights(
                current=[{"category": "food", "amount": 50, "merchant": "New Restaurant"}],
                previous=[],
            )
            assert any("new merchant" in i.what_changed.lower() for i in insights)

    def test_price_increase(self, app, db_session):
        with app.app_context():
            prev = [{"category": "food", "amount": 10, "merchant": "Starbucks"}] * 3
            curr = [{"category": "food", "amount": 20, "merchant": "Starbucks"}] * 3
            insights = generate_insights(curr, prev)
            assert any("starbucks" in i.what_changed.lower() for i in insights)


class TestSummary:
    def test_empty(self):
        result = get_spending_summary([])
        assert result["total"] == 0

    def test_with_data(self):
        txs = [
            {"category": "food", "amount": 20, "merchant": "A"},
            {"category": "food", "amount": 30, "merchant": "B"},
            {"category": "transport", "amount": 15, "merchant": "C"},
        ]
        result = get_spending_summary(txs)
        assert result["total"] == 65
        assert result["count"] == 3
        assert "food" in result["categories"]
