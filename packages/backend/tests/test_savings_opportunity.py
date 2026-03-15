"""Tests for savings opportunity detection engine."""

import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models import SavingsOpportunity, Expense, Category


def _create_category(client, name="Food"):
    """Helper to create a category in db."""
    with client.application.app_context():
        cat = Category(name=name, user_id=1)
        db.session.add(cat)
        db.session.commit()
        return cat.id


def _create_expense(client, user_id=1, amount=100, category_id=None, days_ago=0):
    """Helper to create an expense in db."""
    with client.application.app_context():
        exp = Expense(
            user_id=user_id,
            notes="Test expense",
            amount=amount,
            category_id=category_id,
            spent_at=datetime.utcnow() - timedelta(days=days_ago),
        )
        db.session.add(exp)
        db.session.commit()
        return exp.id


def _create_opportunity(client, user_id=1, **kwargs):
    """Helper to create an opportunity in db."""
    with client.application.app_context():
        defaults = {
            "user_id": user_id,
            "type": "spending_spike",
            "title": "Test opportunity",
            "description": "Test description",
            "current_amount": 200,
            "target_amount": 100,
            "potential_savings": 100,
            "confidence": 0.8,
        }
        defaults.update(kwargs)
        opp = SavingsOpportunity(**defaults)
        db.session.add(opp)
        db.session.commit()
        return opp.id


# ═══════════════════════════════════════════════════════════════════
# Service unit tests
# ═══════════════════════════════════════════════════════════════════


class TestDetectSpendingSpikes:
    """Test spending spike detection."""

    def test_no_expenses(self, client, auth_header):
        from app.services.savings_opportunity import detect_spending_spikes

        with client.application.app_context():
            result = detect_spending_spikes(1)

        assert result == []

    def test_detects_spike(self, client, auth_header):
        from app.services.savings_opportunity import detect_spending_spikes

        cat_id = _create_category(client, "Dining")
        # Historical: 3 periods of $100 each (avg = $100)
        for d in [35, 45, 55, 65, 75, 85]:
            _create_expense(client, amount=50, category_id=cat_id, days_ago=d)
        # Recent: $200 (2x average, above 1.5 threshold)
        _create_expense(client, amount=200, category_id=cat_id, days_ago=5)

        with client.application.app_context():
            result = detect_spending_spikes(1, days=30, threshold=1.5)

        assert len(result) >= 1
        assert result[0]["type"] == "spending_spike"
        assert result[0]["potential_savings"] > 0

    def test_no_spike_below_threshold(self, client, auth_header):
        from app.services.savings_opportunity import detect_spending_spikes

        cat_id = _create_category(client, "Groceries")
        # Historical and recent are similar
        for d in [5, 35, 65]:
            _create_expense(client, amount=100, category_id=cat_id, days_ago=d)

        with client.application.app_context():
            result = detect_spending_spikes(1, days=30)

        # Should not flag since spending is normal
        assert result == []


class TestDetectCategoryOverspend:
    """Test category overspend detection."""

    def test_no_expenses(self, client, auth_header):
        from app.services.savings_opportunity import detect_category_overspend

        with client.application.app_context():
            result = detect_category_overspend(1)

        assert result == []

    def test_detects_overspend(self, client, auth_header):
        from app.services.savings_opportunity import detect_category_overspend

        cat1 = _create_category(client, "Entertainment")
        cat2 = _create_category(client, "Groceries")
        # Entertainment is 80% of spending
        _create_expense(client, amount=800, category_id=cat1, days_ago=5)
        _create_expense(client, amount=200, category_id=cat2, days_ago=5)

        with client.application.app_context():
            result = detect_category_overspend(1, days=30)

        assert len(result) >= 1
        assert result[0]["type"] == "category_overspend"

    def test_balanced_spending_ok(self, client, auth_header):
        from app.services.savings_opportunity import detect_category_overspend

        cat1 = _create_category(client, "Food")
        cat2 = _create_category(client, "Transport")
        cat3 = _create_category(client, "Utilities")
        _create_expense(client, amount=100, category_id=cat1, days_ago=5)
        _create_expense(client, amount=100, category_id=cat2, days_ago=5)
        _create_expense(client, amount=100, category_id=cat3, days_ago=5)

        with client.application.app_context():
            result = detect_category_overspend(1, days=30)

        assert result == []


class TestFullDetection:
    """Test combined detection."""

    def test_run_full_detection(self, client, auth_header):
        from app.services.savings_opportunity import run_full_detection

        with client.application.app_context():
            result = run_full_detection(1)

        assert isinstance(result, list)

    def test_sorted_by_savings(self, client, auth_header):
        from app.services.savings_opportunity import run_full_detection

        cat1 = _create_category(client, "Big")
        cat2 = _create_category(client, "Small")
        _create_expense(client, amount=900, category_id=cat1, days_ago=5)
        _create_expense(client, amount=100, category_id=cat2, days_ago=5)

        with client.application.app_context():
            result = run_full_detection(1)

        if len(result) >= 2:
            assert result[0]["potential_savings"] >= result[1]["potential_savings"]


class TestOpportunityManagement:
    """Test CRUD operations on opportunities."""

    def test_get_opportunities_empty(self, client, auth_header):
        from app.services.savings_opportunity import get_opportunities

        with client.application.app_context():
            result = get_opportunities(1)

        assert result == []

    def test_get_opportunities(self, client, auth_header):
        from app.services.savings_opportunity import get_opportunities

        _create_opportunity(client)
        with client.application.app_context():
            result = get_opportunities(1)

        assert len(result) == 1
        assert result[0]["type"] == "spending_spike"

    def test_get_opportunity_detail(self, client, auth_header):
        from app.services.savings_opportunity import get_opportunity

        oid = _create_opportunity(client)
        with client.application.app_context():
            result = get_opportunity(oid, 1)

        assert result is not None
        assert result["id"] == oid

    def test_get_nonexistent(self, client, auth_header):
        from app.services.savings_opportunity import get_opportunity

        with client.application.app_context():
            assert get_opportunity(9999, 1) is None

    def test_dismiss(self, client, auth_header):
        from app.services.savings_opportunity import dismiss_opportunity

        oid = _create_opportunity(client)
        with client.application.app_context():
            result = dismiss_opportunity(oid, 1)

        assert result["is_dismissed"] is True
        assert result["status"] == "dismissed"

    def test_dismiss_nonexistent(self, client, auth_header):
        from app.services.savings_opportunity import dismiss_opportunity

        with client.application.app_context():
            assert dismiss_opportunity(9999, 1) is None

    def test_mark_action_taken(self, client, auth_header):
        from app.services.savings_opportunity import mark_action_taken

        oid = _create_opportunity(client)
        with client.application.app_context():
            result = mark_action_taken(oid, 1)

        assert result["action_taken"] is True
        assert result["status"] == "acted"

    def test_filter_by_type(self, client, auth_header):
        from app.services.savings_opportunity import get_opportunities

        _create_opportunity(client, type="spending_spike")
        _create_opportunity(client, type="category_overspend", title="Overspend")

        with client.application.app_context():
            result = get_opportunities(1, type="category_overspend")

        assert len(result) == 1
        assert result[0]["type"] == "category_overspend"


class TestSavingsSummary:
    """Test summary calculations."""

    def test_empty_summary(self, client, auth_header):
        from app.services.savings_opportunity import get_savings_summary

        with client.application.app_context():
            result = get_savings_summary(1)

        assert result["total_opportunities"] == 0
        assert result["total_potential_savings"] == 0
        assert result["avg_confidence"] == 0.0

    def test_summary_with_data(self, client, auth_header):
        from app.services.savings_opportunity import get_savings_summary, mark_action_taken

        oid1 = _create_opportunity(client, potential_savings=100, confidence=0.8)
        _create_opportunity(client, potential_savings=200, confidence=0.6,
                           type="category_overspend", title="Overspend")

        with client.application.app_context():
            mark_action_taken(oid1, 1)
            result = get_savings_summary(1)

        assert result["total_opportunities"] == 2
        assert result["total_potential_savings"] == 300.0
        assert result["acted_count"] == 1
        assert result["acted_savings"] == 100.0
        assert result["by_type"]["spending_spike"]["count"] == 1


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestSavingsRoutes:
    """Integration tests for /savings/* endpoints."""

    # ── POST /savings/detect ──
    def test_detect_route(self, client, auth_header):
        r = client.post("/savings/detect", json={}, headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "opportunities" in body
        assert "count" in body

    def test_detect_with_days(self, client, auth_header):
        r = client.post("/savings/detect",
                        json={"days": 7},
                        headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["period_days"] == 7

    def test_detect_unauthorized(self, client):
        r = client.post("/savings/detect", json={})
        assert r.status_code == 401

    # ── GET /savings ──
    def test_list_route(self, client, auth_header):
        r = client.get("/savings", headers=auth_header)
        assert r.status_code == 200
        assert "opportunities" in r.get_json()

    def test_list_with_filters(self, client, auth_header):
        r = client.get("/savings?type=spending_spike&status=active&limit=10",
                       headers=auth_header)
        assert r.status_code == 200

    # ── GET /savings/<id> ──
    def test_get_one_route(self, client, auth_header):
        oid = _create_opportunity(client)
        r = client.get(f"/savings/{oid}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["id"] == oid

    def test_get_nonexistent_route(self, client, auth_header):
        r = client.get("/savings/9999", headers=auth_header)
        assert r.status_code == 404

    # ── POST /savings/<id>/dismiss ──
    def test_dismiss_route(self, client, auth_header):
        oid = _create_opportunity(client)
        r = client.post(f"/savings/{oid}/dismiss", json={}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["is_dismissed"] is True

    def test_dismiss_nonexistent_route(self, client, auth_header):
        r = client.post("/savings/9999/dismiss", json={}, headers=auth_header)
        assert r.status_code == 404

    # ── POST /savings/<id>/act ──
    def test_act_route(self, client, auth_header):
        oid = _create_opportunity(client)
        r = client.post(f"/savings/{oid}/act", json={}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["action_taken"] is True

    # ── GET /savings/summary ──
    def test_summary_route(self, client, auth_header):
        r = client.get("/savings/summary", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "total_potential_savings" in body
        assert "by_type" in body
