"""Tests for Subscription Tracker."""

import pytest


class TestSubscriptionTracker:
    def test_add_subscription(self):
        from app.services.subscription_tracker import SubscriptionTracker
        svc = SubscriptionTracker()
        result = svc.add("user1", "Netflix", 15.99, "monthly", "entertainment")
        assert result["name"] == "Netflix"
        assert result["annual_cost"] == pytest.approx(15.99 * 12, rel=0.1)

    def test_cancel(self):
        from app.services.subscription_tracker import SubscriptionTracker
        svc = SubscriptionTracker()
        sub = svc.add("user1", "Spotify", 9.99, "monthly")
        result = svc.cancel(sub["sub_id"])
        assert result["status"] == "cancelled"

    def test_summary(self):
        from app.services.subscription_tracker import SubscriptionTracker
        svc = SubscriptionTracker()
        svc.add("user1", "Netflix", 15.99, "monthly", "entertainment")
        svc.add("user1", "AWS", 50.0, "monthly", "cloud")
        svc.add("user1", "NYT", 20.0, "yearly", "news")
        summary = svc.get_summary("user1")
        assert summary["total_active"] == 3
        assert summary["total_annual"] > 0

    def test_usage_tracking(self):
        from app.services.subscription_tracker import SubscriptionTracker
        svc = SubscriptionTracker()
        sub = svc.add("user1", "Gym", 50.0, "monthly")
        svc.record_usage(sub["sub_id"], used=False)
        svc.record_usage(sub["sub_id"], used=False)
        svc.record_usage(sub["sub_id"], used=False)
        svc.record_usage(sub["sub_id"], used=False)
        summary = svc.get_summary("user1")
        assert len(summary["potentially_unused"]) == 1

    def test_trial_tracking(self):
        from app.services.subscription_tracker import SubscriptionTracker
        from datetime import datetime, timedelta
        svc = SubscriptionTracker()
        trial_end = (datetime.utcnow() + timedelta(days=3)).isoformat()[:10]
        svc.add("user1", "Adobe", 54.99, "monthly", "software",
                is_trial=True, trial_end=trial_end)
        summary = svc.get_summary("user1")
        assert len(summary["trials_ending_soon"]) == 1

    def test_yearly_subscription(self):
        from app.services.subscription_tracker import SubscriptionTracker
        svc = SubscriptionTracker()
        result = svc.add("user1", "Costco", 60.0, "yearly", "membership")
        assert result["annual_cost"] == 60.0
        assert result["monthly_cost"] == pytest.approx(5.0, rel=0.1)
