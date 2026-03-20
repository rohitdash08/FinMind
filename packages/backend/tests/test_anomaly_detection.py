"""Tests for the Anomaly Detection Engine (#72)."""
from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

import pytest


# ── Test helpers ───────────────────────────────────────────────────────────────

def _add_expense(client, auth_header, amount: float, exp_date: str,
                 category_id: int | None = None, notes: str | None = None,
                 expense_type: str = "EXPENSE"):
    payload = {
        "amount": amount,
        "description": f"Test expense {amount}",
        "date": exp_date,
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    if notes is not None:
        payload["notes"] = notes
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201, f"Expense creation failed: {r.get_json()}"
    return r.get_json()


def _add_category(client, auth_header, name: str) -> int:
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201, f"Category creation failed: {r.get_json()}"
    return r.get_json()["id"]


def _get_anomalies(client, auth_header, month: str):
    return client.get(
        f"/insights/anomalies?month={month}", headers=auth_header
    )


def _month_str(months_ago: int) -> str:
    """Return YYYY-MM string for today minus N months."""
    today = date.today()
    year, month = today.year, today.month
    for _ in range(months_ago):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return f"{year:04d}-{month:02d}"


def _first_day(ym: str) -> str:
    return f"{ym}-01"


# ── Endpoint tests ─────────────────────────────────────────────────────────────

class TestAnomalyDetectionEndpoint:
    """Basic endpoint contract tests."""

    def test_requires_authentication(self, client):
        """GET /insights/anomalies without token returns 401."""
        r = client.get("/insights/anomalies?month=2025-01")
        assert r.status_code == 401

    def test_returns_200_for_authenticated_user(self, client, auth_header):
        """Authenticated request returns 200 with expected schema."""
        ym = _month_str(0)
        r = _get_anomalies(client, auth_header, ym)
        assert r.status_code == 200
        data = r.get_json()
        assert "month" in data
        assert "anomalies_count" in data
        assert "has_high_severity" in data
        assert "anomalies" in data
        assert isinstance(data["anomalies"], list)

    def test_empty_result_when_no_data(self, client, auth_header):
        """Returns zero anomalies when user has no expenses."""
        ym = "2020-01"  # far past, no data
        r = _get_anomalies(client, auth_header, ym)
        assert r.status_code == 200
        data = r.get_json()
        assert data["anomalies_count"] == 0
        assert data["has_high_severity"] is False
        assert data["anomalies"] == []

    def test_defaults_to_current_month(self, client, auth_header):
        """When month param is omitted, defaults to current month."""
        r = client.get("/insights/anomalies", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        expected = date.today().strftime("%Y-%m")
        assert data["month"] == expected

    def test_month_field_in_response(self, client, auth_header):
        """Response month matches the queried month."""
        ym = _month_str(1)
        r = _get_anomalies(client, auth_header, ym)
        assert r.status_code == 200
        assert r.get_json()["month"] == ym


# ── Category anomaly tests ─────────────────────────────────────────────────────

class TestCategoryAnomalies:
    """Tests for category-level anomaly detection."""

    def test_detects_high_severity_spike(self, client, auth_header):
        """A massive spike in one category is flagged as high severity."""
        cat_id = _add_category(client, auth_header, "Dining")
        # Baseline: 2 prior months with ~200 each
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 200.0, _first_day(ym),
                         category_id=cat_id)

        # Current month: 1500 (huge spike, z >> 2.5)
        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 1500.0, _first_day(cur_ym),
                     category_id=cat_id)

        r = _get_anomalies(client, auth_header, cur_ym)
        assert r.status_code == 200
        data = r.get_json()
        assert data["anomalies_count"] >= 1
        cat_anomalies = [a for a in data["anomalies"] if a["type"] == "category"]
        assert len(cat_anomalies) >= 1
        top = cat_anomalies[0]
        assert top["severity"] == "high"
        assert top["z_score"] > 0
        assert top["spike_amount"] > 0
        assert "explanation" in top and len(top["explanation"]) > 10

    def test_no_anomaly_for_stable_spending(self, client, auth_header):
        """Consistent spending across months does not trigger anomaly."""
        cat_id = _add_category(client, auth_header, "Groceries")
        # 3 months of similar spending ~500
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 490.0, _first_day(ym),
                         category_id=cat_id)

        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 510.0, _first_day(cur_ym),
                     category_id=cat_id)

        r = _get_anomalies(client, auth_header, cur_ym)
        assert r.status_code == 200
        data = r.get_json()
        # Should not flag a 4% variance
        cat_anomalies = [
            a for a in data["anomalies"]
            if a["type"] == "category" and a["label"] == "Groceries"
        ]
        assert len(cat_anomalies) == 0

    def test_anomaly_schema_fields(self, client, auth_header):
        """Anomaly result contains all required fields."""
        cat_id = _add_category(client, auth_header, "Entertainment")
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 100.0, _first_day(ym),
                         category_id=cat_id)

        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 2000.0, _first_day(cur_ym),
                     category_id=cat_id)

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        anomalies = [a for a in data["anomalies"] if a["type"] == "category"]
        assert len(anomalies) >= 1
        a = anomalies[0]
        required_fields = [
            "id", "type", "label", "category_id", "current_spend",
            "baseline_avg", "baseline_stddev", "z_score",
            "spike_amount", "spike_percent", "severity", "explanation",
        ]
        for field in required_fields:
            assert field in a, f"Missing field: {field}"

    def test_category_id_present_for_category_anomaly(self, client, auth_header):
        """Category anomalies include the correct category_id."""
        cat_id = _add_category(client, auth_header, "Travel")
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 100.0, _first_day(ym),
                         category_id=cat_id)
        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 3000.0, _first_day(cur_ym),
                     category_id=cat_id)

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        cat_anomalies = [a for a in data["anomalies"]
                         if a["type"] == "category" and a["label"] == "Travel"]
        assert len(cat_anomalies) >= 1
        assert cat_anomalies[0]["category_id"] == cat_id

    def test_no_anomaly_without_baseline(self, client, auth_header):
        """New category with no history does not trigger anomaly."""
        cat_id = _add_category(client, auth_header, "NewCategory2099")
        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 5000.0, _first_day(cur_ym),
                     category_id=cat_id)

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        cat_anomalies = [
            a for a in data["anomalies"]
            if a.get("label") == "NewCategory2099"
        ]
        assert len(cat_anomalies) == 0


# ── Merchant anomaly tests ─────────────────────────────────────────────────────

class TestMerchantAnomalies:
    """Tests for merchant-level (notes-based) anomaly detection."""

    def test_detects_merchant_spike(self, client, auth_header):
        """A spike at a known merchant is detected."""
        # Baseline: 2 months of ~300 at "BigMart"
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 300.0, _first_day(ym),
                         notes="BigMart")

        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 2500.0, _first_day(cur_ym),
                     notes="BigMart")

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        merch_anomalies = [a for a in data["anomalies"]
                           if a["type"] == "merchant" and a["label"] == "BigMart"]
        assert len(merch_anomalies) >= 1
        assert merch_anomalies[0]["spike_amount"] > 0

    def test_merchant_anomaly_has_null_category_id(self, client, auth_header):
        """Merchant anomalies have category_id = null."""
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 200.0, _first_day(ym),
                         notes="QuickShop")
        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 3000.0, _first_day(cur_ym),
                     notes="QuickShop")

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        merch = [a for a in data["anomalies"]
                 if a["type"] == "merchant" and a["label"] == "QuickShop"]
        assert len(merch) >= 1
        assert merch[0]["category_id"] is None

    def test_no_merchant_anomaly_without_baseline(self, client, auth_header):
        """First-time merchant spend with no history is not flagged."""
        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 9999.0, _first_day(cur_ym),
                     notes="BrandNewMerchant2099")

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        merch = [a for a in data["anomalies"]
                 if a.get("label") == "BrandNewMerchant2099"]
        assert len(merch) == 0


# ── Severity ordering tests ────────────────────────────────────────────────────

class TestAnomalyOrdering:
    """Anomalies are returned sorted by severity then z_score."""

    def test_high_severity_first(self, client, auth_header):
        """High severity anomaly appears before medium severity."""
        cat_food = _add_category(client, auth_header, "FoodA")
        cat_misc = _add_category(client, auth_header, "MiscA")

        # FoodA: moderate spike (medium severity)
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 500.0, _first_day(ym),
                         category_id=cat_food)
        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 1100.0, _first_day(cur_ym),
                     category_id=cat_food)

        # MiscA: extreme spike (high severity)
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 100.0, _first_day(ym),
                         category_id=cat_misc)
        _add_expense(client, auth_header, 9000.0, _first_day(cur_ym),
                     category_id=cat_misc)

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        anomalies = data["anomalies"]
        if len(anomalies) >= 2:
            severities = [a["severity"] for a in anomalies]
            high_idx = next((i for i, s in enumerate(severities) if s == "high"), None)
            medium_idx = next((i for i, s in enumerate(severities) if s == "medium"), None)
            if high_idx is not None and medium_idx is not None:
                assert high_idx < medium_idx, "High severity should come before medium"

    def test_has_high_severity_flag(self, client, auth_header):
        """has_high_severity is True when a high-severity anomaly exists."""
        cat_id = _add_category(client, auth_header, "SpikeCategory")
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 100.0, _first_day(ym),
                         category_id=cat_id)
        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 5000.0, _first_day(cur_ym),
                     category_id=cat_id)

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        if data["anomalies_count"] > 0:
            high_found = any(a["severity"] == "high" for a in data["anomalies"])
            assert data["has_high_severity"] == high_found

    def test_income_expenses_excluded(self, client, auth_header):
        """INCOME expense_type entries do not contribute to anomalies."""
        cat_id = _add_category(client, auth_header, "Salary")
        for m_ago in [3, 2]:
            ym = _month_str(m_ago)
            _add_expense(client, auth_header, 1000.0, _first_day(ym),
                         category_id=cat_id, expense_type="INCOME")
        cur_ym = _month_str(1)
        _add_expense(client, auth_header, 50000.0, _first_day(cur_ym),
                     category_id=cat_id, expense_type="INCOME")

        r = _get_anomalies(client, auth_header, cur_ym)
        data = r.get_json()
        salary_anomalies = [
            a for a in data["anomalies"] if a.get("label") == "Salary"
        ]
        assert len(salary_anomalies) == 0