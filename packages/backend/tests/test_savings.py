"""Tests for the Savings Opportunity Detection engine."""

from datetime import date, timedelta
from decimal import Decimal


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (200, 201), f"category create failed: {r.get_json()}"
    return r.get_json()["id"]


def _add_expense(client, auth_header, amount, category_id, spent_at, notes="test"):
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "category_id": category_id,
            "spent_at": spent_at.isoformat(),
            "notes": notes,
        },
        headers=auth_header,
    )
    assert r.status_code in (200, 201), f"expense create failed: {r.get_json()}"
    return r.get_json()


def _add_recurring(client, auth_header, amount, category_id, notes="recurring", cadence="MONTHLY"):
    r = client.post(
        "/expenses/recurring",
        json={
            "amount": amount,
            "category_id": category_id,
            "notes": notes,
            "cadence": cadence,
            "start_date": date.today().isoformat(),
        },
        headers=auth_header,
    )
    assert r.status_code in (200, 201), f"recurring create failed: {r.get_json()}"
    return r.get_json()


class TestSavingsOpportunitiesEndpoint:
    """Tests for GET /savings/opportunities"""

    def test_returns_empty_when_no_data(self, client, auth_header):
        r = client.get("/savings/opportunities", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["opportunity_count"] == 0
        assert data["opportunities"] == []
        assert data["total_estimated_monthly_saving"] == 0

    def test_detects_top_spenders(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Food")
        today = date.today()
        _add_expense(client, auth_header, "5000.00", cat_id, today, notes="Groceries")
        _add_expense(client, auth_header, "3000.00", cat_id, today - timedelta(days=5), notes="Restaurant")

        r = client.get("/savings/opportunities", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        # Should have at least a top_spender opportunity
        types = [o["type"] for o in data["opportunities"]]
        assert "top_spender" in types

    def test_detects_spiking_category(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Entertainment")
        today = date.today()

        # 3 months of low spending (~100/mo)
        for months_ago in range(3, 0, -1):
            d = today - timedelta(days=30 * months_ago)
            _add_expense(client, auth_header, "100.00", cat_id, d, notes="monthly")

        # Current month: spike to 500
        _add_expense(client, auth_header, "500.00", cat_id, today, notes="big spend")

        r = client.get("/savings/opportunities", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        types = [o["type"] for o in data["opportunities"]]
        assert "spiking_category" in types

    def test_detects_increasing_trend(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Shopping")
        today = date.today()

        # 6 months of steadily increasing spend
        for i in range(5, -1, -1):
            amount = str(100 + (5 - i) * 50)  # 100, 150, 200, 250, 300, 350
            d = today - timedelta(days=30 * i)
            _add_expense(client, auth_header, f"{amount}.00", cat_id, d, notes=f"month {i}")

        r = client.get("/savings/opportunities", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        types = [o["type"] for o in data["opportunities"]]
        assert "trend_increase" in types

    def test_detects_duplicate_recurring(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Subscriptions")

        # Two recurring expenses with almost identical amounts
        _add_recurring(client, auth_header, "499.00", cat_id, notes="Netflix", cadence="MONTHLY")
        _add_recurring(client, auth_header, "500.00", cat_id, notes="Hulu", cadence="MONTHLY")

        r = client.get("/savings/opportunities", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        types = [o["type"] for o in data["opportunities"]]
        assert "duplicate_recurring" in types

    def test_response_structure(self, client, auth_header):
        r = client.get("/savings/opportunities", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "opportunities" in data
        assert "total_estimated_monthly_saving" in data
        assert "opportunity_count" in data
        assert "analysis_months" in data
        assert isinstance(data["opportunities"], list)
        assert isinstance(data["total_estimated_monthly_saving"], (int, float))
        assert isinstance(data["opportunity_count"], int)

    def test_requires_auth(self, client):
        r = client.get("/savings/opportunities")
        assert r.status_code == 401


class TestSavingsService:
    """Unit tests for the savings detection functions."""

    def test_empty_monthly_no_spiking(self):
        from app.services.savings import _detect_spiking_categories
        result = _detect_spiking_categories([])
        assert result == []

    def test_spiking_requires_4_months(self):
        from app.services.savings import _detect_spiking_categories
        # Only 3 months of data — should return empty
        monthly = [
            {"year_month": "2025-01", "total": 100, "by_category": {"Food": 100}},
            {"year_month": "2025-02", "total": 100, "by_category": {"Food": 100}},
            {"year_month": "2025-03", "total": 500, "by_category": {"Food": 500}},
        ]
        result = _detect_spiking_categories(monthly)
        assert result == []

    def test_spiking_detected(self):
        from app.services.savings import _detect_spiking_categories
        monthly = [
            {"year_month": "2024-12", "total": 100, "by_category": {"Food": 100}},
            {"year_month": "2025-01", "total": 110, "by_category": {"Food": 110}},
            {"year_month": "2025-02", "total": 90, "by_category": {"Food": 90}},
            {"year_month": "2025-03", "total": 300, "by_category": {"Food": 300}},
        ]
        result = _detect_spiking_categories(monthly)
        assert len(result) == 1
        assert result[0].type == "spiking_category"
        assert "Food" in result[0].title

    def test_top_spender_detection(self):
        from app.services.savings import _detect_top_spenders
        monthly = [
            {
                "year_month": "2025-03",
                "total": 1500,
                "by_category": {"Food": 800, "Transport": 500, "Other": 200},
            }
        ]
        result = _detect_top_spenders(monthly)
        assert len(result) == 3
        assert all(o.type == "top_spender" for o in result)
        # First should be the highest spender
        assert result[0].category == "Food"
        assert result[0].estimated_monthly_saving == 80.0  # 10% of 800

    def test_trend_detection_no_data(self):
        from app.services.savings import _detect_increasing_trends
        result = _detect_increasing_trends([])
        assert result == []
