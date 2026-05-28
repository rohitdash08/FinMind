"""
Tests for subscription detection and cost monitoring.
"""

import pytest
from datetime import datetime, timedelta
from app.services.subscription_detector import (
    detect_subscriptions,
    get_user_subscriptions,
    get_cost_alerts,
    confirm_subscription,
)


class TestSubscriptionDetection:
    def test_detect_monthly(self, app, db_session):
        with app.app_context():
            base = datetime.utcnow()
            txs = [
                {"merchant": "Netflix", "amount": 15.99, "date": base - timedelta(days=60)},
                {"merchant": "Netflix", "amount": 15.99, "date": base - timedelta(days=30)},
                {"merchant": "Netflix", "amount": 15.99, "date": base},
            ]
            results = detect_subscriptions(1, txs)
            assert len(results) == 1
            assert results[0].merchant == "netflix"
            assert results[0].frequency == "monthly"
            assert results[0].confidence > 0.5

    def test_detect_yearly(self, app, db_session):
        with app.app_context():
            base = datetime.utcnow()
            txs = [
                {"merchant": "Amazon Prime", "amount": 139, "date": base - timedelta(days=730)},
                {"merchant": "Amazon Prime", "amount": 139, "date": base - timedelta(days=365)},
                {"merchant": "Amazon Prime", "amount": 139, "date": base},
            ]
            results = detect_subscriptions(1, txs)
            assert len(results) == 1
            assert results[0].frequency == "yearly"

    def test_no_detect_single(self, app, db_session):
        with app.app_context():
            txs = [{"merchant": "Random", "amount": 50, "date": datetime.utcnow()}]
            results = detect_subscriptions(1, txs)
            assert len(results) == 0

    def test_multiple_subscriptions(self, app, db_session):
        with app.app_context():
            base = datetime.utcnow()
            txs = [
                {"merchant": "Spotify", "amount": 9.99, "date": base - timedelta(days=30)},
                {"merchant": "Spotify", "amount": 9.99, "date": base},
                {"merchant": "Gym", "amount": 50, "date": base - timedelta(days=30)},
                {"merchant": "Gym", "amount": 50, "date": base},
            ]
            results = detect_subscriptions(1, txs)
            assert len(results) == 2


class TestCostIncrease:
    def test_cost_increase_alert(self, app, db_session):
        with app.app_context():
            base = datetime.utcnow()
            # First detection
            txs1 = [
                {"merchant": "Netflix", "amount": 15.99, "date": base - timedelta(days=60)},
                {"merchant": "Netflix", "amount": 15.99, "date": base - timedelta(days=30)},
            ]
            detect_subscriptions(1, txs1)

            # Price increase
            txs2 = [
                {"merchant": "Netflix", "amount": 22.99, "date": base - timedelta(days=15)},
                {"merchant": "Netflix", "amount": 22.99, "date": base},
            ]
            detect_subscriptions(1, txs2)

            alerts = get_cost_alerts(1)
            assert len(alerts) >= 1
            assert alerts[0].old_amount == 15.99
            assert alerts[0].new_amount > 15.99


class TestConfirmDismiss:
    def test_confirm(self, app, db_session):
        with app.app_context():
            base = datetime.utcnow()
            txs = [
                {"merchant": "Netflix", "amount": 15.99, "date": base - timedelta(days=30)},
                {"merchant": "Netflix", "amount": 15.99, "date": base},
            ]
            results = detect_subscriptions(1, txs)
            sub = confirm_subscription(results[0].id, 1)
            assert sub.is_confirmed is True
