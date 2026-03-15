"""Tests for subscription cost increase detection."""

import pytest
from app.models import (
    SubscriptionPlan,
    UserSubscription,
    SubscriptionPriceHistory,
    SubscriptionCostAlert,
    User,
)
from app.extensions import db
from app.services.subscription_cost import (
    update_plan_price,
    get_price_history,
    get_all_price_changes,
    get_user_alerts,
    acknowledge_alert,
    acknowledge_all_alerts,
    get_user_cost_summary,
    detect_increases,
)


# ── Helpers ───────────────────────────────────────────────────────


def _create_plan(name="Pro", price_cents=999, interval="monthly"):
    plan = SubscriptionPlan(name=name, price_cents=price_cents, interval=interval)
    db.session.add(plan)
    db.session.commit()
    return plan


def _create_user(email="sub@test.com"):
    from werkzeug.security import generate_password_hash
    user = User(email=email, password_hash=generate_password_hash("pass123"))
    db.session.add(user)
    db.session.commit()
    return user


def _subscribe(user_id, plan_id, active=True):
    sub = UserSubscription(user_id=user_id, plan_id=plan_id, active=active)
    db.session.add(sub)
    db.session.commit()
    return sub


# ── Service: update_plan_price ────────────────────────────────────


class TestUpdatePlanPrice:
    def test_plan_not_found(self, app_fixture):
        with app_fixture.app_context():
            result = update_plan_price(999, 1500)
            assert result["error"] == "Plan not found"

    def test_no_change(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            result = update_plan_price(plan.id, 999)
            assert result["changed"] is False
            assert result["price_cents"] == 999

    def test_price_increase(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            result = update_plan_price(plan.id, 1499)
            assert result["changed"] is True
            assert result["direction"] == "increase"
            assert result["old_price_cents"] == 999
            assert result["new_price_cents"] == 1499
            assert result["change_pct"] > 0

    def test_price_decrease(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            result = update_plan_price(plan.id, 799)
            assert result["changed"] is True
            assert result["direction"] == "decrease"

    def test_increase_creates_history(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            update_plan_price(plan.id, 1499)
            history = SubscriptionPriceHistory.query.filter_by(plan_id=plan.id).all()
            assert len(history) == 1
            assert history[0].old_price_cents == 999
            assert history[0].new_price_cents == 1499

    def test_increase_alerts_subscribers(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            user = _create_user()
            _subscribe(user.id, plan.id)
            result = update_plan_price(plan.id, 1499)
            assert result["alerts_created"] == 1
            alerts = SubscriptionCostAlert.query.filter_by(user_id=user.id).all()
            assert len(alerts) == 1

    def test_decrease_no_alerts(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            user = _create_user()
            _subscribe(user.id, plan.id)
            result = update_plan_price(plan.id, 799)
            assert result["alerts_created"] == 0

    def test_inactive_subscribers_not_alerted(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            user = _create_user()
            _subscribe(user.id, plan.id, active=False)
            result = update_plan_price(plan.id, 1499)
            assert result["alerts_created"] == 0

    def test_multiple_subscribers_alerted(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            u1 = _create_user("user1@test.com")
            u2 = _create_user("user2@test.com")
            _subscribe(u1.id, plan.id)
            _subscribe(u2.id, plan.id)
            result = update_plan_price(plan.id, 1499)
            assert result["alerts_created"] == 2


# ── Service: get_price_history ────────────────────────────────────


class TestPriceHistory:
    def test_empty_history(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan()
            result = get_price_history(plan.id)
            assert result == []

    def test_history_after_changes(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=500)
            update_plan_price(plan.id, 600)
            update_plan_price(plan.id, 700)
            result = get_price_history(plan.id)
            assert len(result) == 2
            # Most recent first
            assert result[0]["new_price_cents"] == 700

    def test_all_price_changes(self, app_fixture):
        with app_fixture.app_context():
            p1 = _create_plan("Plan A", 500)
            p2 = _create_plan("Plan B", 800)
            update_plan_price(p1.id, 600)
            update_plan_price(p2.id, 900)
            result = get_all_price_changes()
            assert len(result) == 2


# ── Service: alerts ───────────────────────────────────────────────


class TestAlerts:
    def test_get_user_alerts_empty(self, app_fixture):
        with app_fixture.app_context():
            result = get_user_alerts(999)
            assert result == []

    def test_get_user_alerts(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            user = _create_user()
            _subscribe(user.id, plan.id)
            update_plan_price(plan.id, 1499)
            result = get_user_alerts(user.id)
            assert len(result) == 1
            assert result[0]["old_price_cents"] == 999

    def test_unacknowledged_only(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            user = _create_user()
            _subscribe(user.id, plan.id)
            update_plan_price(plan.id, 1499)
            # Acknowledge the first
            alerts = get_user_alerts(user.id)
            acknowledge_alert(user.id, alerts[0]["id"])
            # Should be empty when filtering unacknowledged
            result = get_user_alerts(user.id, unacknowledged_only=True)
            assert len(result) == 0

    def test_acknowledge_alert(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            user = _create_user()
            _subscribe(user.id, plan.id)
            update_plan_price(plan.id, 1499)
            alerts = get_user_alerts(user.id)
            result = acknowledge_alert(user.id, alerts[0]["id"])
            assert result["acknowledged"] is True

    def test_acknowledge_alert_not_found(self, app_fixture):
        with app_fixture.app_context():
            result = acknowledge_alert(1, 999)
            assert "error" in result

    def test_acknowledge_all(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=500)
            user = _create_user()
            _subscribe(user.id, plan.id)
            update_plan_price(plan.id, 600)
            update_plan_price(plan.id, 700)
            result = acknowledge_all_alerts(user.id)
            assert result["acknowledged_count"] == 2


# ── Service: cost summary ────────────────────────────────────────


class TestCostSummary:
    def test_empty_summary(self, app_fixture):
        with app_fixture.app_context():
            result = get_user_cost_summary(999)
            assert result["total_monthly_cents"] == 0
            assert result["subscription_count"] == 0

    def test_monthly_plan_summary(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan("Pro", 999, "monthly")
            user = _create_user()
            _subscribe(user.id, plan.id)
            result = get_user_cost_summary(user.id)
            assert result["total_monthly_cents"] == 999
            assert result["subscription_count"] == 1

    def test_yearly_plan_normalized(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan("Annual", 12000, "yearly")
            user = _create_user()
            _subscribe(user.id, plan.id)
            result = get_user_cost_summary(user.id)
            assert result["total_monthly_cents"] == 1000  # 12000/12

    def test_weekly_plan_normalized(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan("Weekly", 250, "weekly")
            user = _create_user()
            _subscribe(user.id, plan.id)
            result = get_user_cost_summary(user.id)
            assert result["total_monthly_cents"] == 1000  # 250 * 4

    def test_summary_includes_recent_increases(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan("Pro", 999, "monthly")
            user = _create_user()
            _subscribe(user.id, plan.id)
            update_plan_price(plan.id, 1499)
            result = get_user_cost_summary(user.id)
            assert len(result["recent_increases"]) == 1


# ── Service: detect_increases ─────────────────────────────────────


class TestDetectIncreases:
    def test_no_increases(self, app_fixture):
        with app_fixture.app_context():
            result = detect_increases()
            assert result == []

    def test_detect_increase(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=500)
            update_plan_price(plan.id, 700)
            result = detect_increases()
            assert len(result) == 1
            assert result[0]["change_pct"] > 0

    def test_filter_by_plan(self, app_fixture):
        with app_fixture.app_context():
            p1 = _create_plan("A", 500)
            p2 = _create_plan("B", 800)
            update_plan_price(p1.id, 600)
            update_plan_price(p2.id, 900)
            result = detect_increases(plan_id=p1.id)
            assert len(result) == 1
            assert result[0]["plan_id"] == p1.id

    def test_decrease_not_detected(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=500)
            update_plan_price(plan.id, 300)
            result = detect_increases()
            assert len(result) == 0


# ── Routes ────────────────────────────────────────────────────────


class TestSubscriptionCostRoutes:
    def _setup_plan(self, app_fixture):
        with app_fixture.app_context():
            plan = _create_plan(price_cents=999)
            return plan.id

    def test_update_price(self, client, auth_header, app_fixture):
        plan_id = self._setup_plan(app_fixture)
        r = client.put(f"/subscriptions/plans/{plan_id}/price",
                       json={"price_cents": 1499},
                       headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["changed"] is True

    def test_update_price_missing_field(self, client, auth_header, app_fixture):
        plan_id = self._setup_plan(app_fixture)
        r = client.put(f"/subscriptions/plans/{plan_id}/price",
                       json={},
                       headers=auth_header)
        assert r.status_code == 400

    def test_update_price_not_found(self, client, auth_header):
        r = client.put("/subscriptions/plans/999/price",
                       json={"price_cents": 1499},
                       headers=auth_header)
        assert r.status_code == 404

    def test_price_history(self, client, auth_header, app_fixture):
        plan_id = self._setup_plan(app_fixture)
        r = client.get(f"/subscriptions/plans/{plan_id}/price-history",
                       headers=auth_header)
        assert r.status_code == 200

    def test_all_price_changes(self, client, auth_header):
        r = client.get("/subscriptions/price-changes",
                       headers=auth_header)
        assert r.status_code == 200

    def test_get_alerts(self, client, auth_header):
        r = client.get("/subscriptions/alerts",
                       headers=auth_header)
        assert r.status_code == 200

    def test_acknowledge_alert_not_found(self, client, auth_header):
        r = client.post("/subscriptions/alerts/999/acknowledge",
                        headers=auth_header)
        assert r.status_code == 404

    def test_acknowledge_all(self, client, auth_header):
        r = client.post("/subscriptions/alerts/acknowledge-all",
                        headers=auth_header)
        assert r.status_code == 200

    def test_cost_summary(self, client, auth_header):
        r = client.get("/subscriptions/summary",
                       headers=auth_header)
        assert r.status_code == 200

    def test_detect_increases(self, client, auth_header):
        r = client.get("/subscriptions/increases",
                       headers=auth_header)
        assert r.status_code == 200

    def test_unauthorized(self, client):
        r = client.get("/subscriptions/alerts")
        assert r.status_code == 401
