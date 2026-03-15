"""Tests for essential vs discretionary spending classification."""

import pytest
from datetime import date, timedelta
from app.services.spending_class import classify_category


# ─── Helpers ────────────────────────────────────────────────────────────


def _create_category(client, auth_header, name="Food"):
    r = client.post(
        "/categories",
        json={"name": name, "monthly_budget": 500},
        headers=auth_header,
    )
    assert r.status_code in (200, 201)
    return r.get_json()["id"]


def _create_expense(client, auth_header, notes="Lunch", amount=12.50,
                     category_id=None, spent_at=None):
    payload = {
        "notes": notes,
        "amount": amount,
        "currency": "USD",
        "expense_type": "EXPENSE",
    }
    if category_id:
        payload["category_id"] = category_id
    if spent_at:
        payload["spent_at"] = spent_at
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code in (200, 201), f"create expense fail: {r.get_json()}"
    return r.get_json()


# ─── classify_category unit tests ───────────────────────────────────────


class TestClassifyCategory:
    """Test auto-classification logic."""

    def test_essential_rent(self):
        assert classify_category("Rent") == "ESSENTIAL"

    def test_essential_groceries(self):
        assert classify_category("Groceries") == "ESSENTIAL"

    def test_essential_healthcare(self):
        assert classify_category("Healthcare") == "ESSENTIAL"

    def test_essential_utilities(self):
        assert classify_category("Utilities") == "ESSENTIAL"

    def test_essential_insurance(self):
        assert classify_category("Insurance") == "ESSENTIAL"

    def test_essential_transport(self):
        assert classify_category("Transportation") == "ESSENTIAL"

    def test_discretionary_dining(self):
        assert classify_category("Dining Out") == "DISCRETIONARY"

    def test_discretionary_entertainment(self):
        assert classify_category("Entertainment") == "DISCRETIONARY"

    def test_discretionary_shopping(self):
        assert classify_category("Shopping") == "DISCRETIONARY"

    def test_discretionary_travel(self):
        assert classify_category("Travel") == "DISCRETIONARY"

    def test_discretionary_gym(self):
        assert classify_category("Gym Membership") == "DISCRETIONARY"

    def test_discretionary_streaming(self):
        assert classify_category("Streaming Services") == "DISCRETIONARY"

    def test_unclassified_misc(self):
        assert classify_category("Miscellaneous") == "UNCLASSIFIED"

    def test_unclassified_random(self):
        assert classify_category("XYZ Random") == "UNCLASSIFIED"

    def test_case_insensitive(self):
        assert classify_category("GROCERIES") == "ESSENTIAL"
        assert classify_category("entertainment") == "DISCRETIONARY"


# ─── Auto-classify endpoint ────────────────────────────────────────────


class TestAutoClassify:
    """Tests for POST /spending/auto-classify."""

    def test_auto_classify_empty(self, client, auth_header):
        """Auto-classify with no categories."""
        r = client.post("/spending/auto-classify", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "classified" in data

    def test_auto_classify_categories(self, client, auth_header):
        """Auto-classify creates correct classifications."""
        _create_category(client, auth_header, "Rent")
        _create_category(client, auth_header, "Entertainment")
        _create_category(client, auth_header, "Random Stuff")

        r = client.post("/spending/auto-classify", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()["classified"]
        assert data["essential"] >= 1
        assert data["discretionary"] >= 1

    def test_auto_classify_idempotent(self, client, auth_header):
        """Second auto-classify doesn't re-classify already classified."""
        _create_category(client, auth_header, "Groceries")

        r1 = client.post("/spending/auto-classify", headers=auth_header)
        assert r1.status_code == 200

        r2 = client.post("/spending/auto-classify", headers=auth_header)
        assert r2.status_code == 200
        # Second time should find 0 to classify
        data = r2.get_json()["classified"]
        assert data["essential"] == 0
        assert data["discretionary"] == 0


# ─── Manual classification endpoint ────────────────────────────────────


class TestManualClassify:
    """Tests for PUT /spending/categories/<id>."""

    def test_set_class(self, client, auth_header):
        """Set spending class manually."""
        cat_id = _create_category(client, auth_header, "Misc")

        r = client.put(
            f"/spending/categories/{cat_id}",
            json={"spending_class": "ESSENTIAL"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["spending_class"] == "ESSENTIAL"

    def test_set_class_discretionary(self, client, auth_header):
        """Set class to discretionary."""
        cat_id = _create_category(client, auth_header, "Misc")

        r = client.put(
            f"/spending/categories/{cat_id}",
            json={"spending_class": "DISCRETIONARY"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["spending_class"] == "DISCRETIONARY"

    def test_set_class_invalid(self, client, auth_header):
        """Invalid class returns 400."""
        cat_id = _create_category(client, auth_header, "Misc")

        r = client.put(
            f"/spending/categories/{cat_id}",
            json={"spending_class": "INVALID"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_set_class_not_found(self, client, auth_header):
        """Non-existent category returns 404."""
        r = client.put(
            "/spending/categories/99999",
            json={"spending_class": "ESSENTIAL"},
            headers=auth_header,
        )
        assert r.status_code == 404

    def test_reclassify(self, client, auth_header):
        """Can change classification from one class to another."""
        cat_id = _create_category(client, auth_header, "Misc")

        r = client.put(
            f"/spending/categories/{cat_id}",
            json={"spending_class": "ESSENTIAL"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["spending_class"] == "ESSENTIAL"

        r = client.put(
            f"/spending/categories/{cat_id}",
            json={"spending_class": "DISCRETIONARY"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["spending_class"] == "DISCRETIONARY"


# ─── List categories by class ──────────────────────────────────────────


class TestListByClass:
    """Tests for GET /spending/categories."""

    def test_list_empty(self, client, auth_header):
        """List with no categories."""
        r = client.get("/spending/categories", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "essential" in data
        assert "discretionary" in data
        assert "unclassified" in data

    def test_list_after_classify(self, client, auth_header):
        """List shows categories in correct groups."""
        _create_category(client, auth_header, "Groceries")
        _create_category(client, auth_header, "Entertainment")

        # Auto-classify
        client.post("/spending/auto-classify", headers=auth_header)

        r = client.get("/spending/categories", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()

        essential_names = [c["name"] for c in data["essential"]]
        discretionary_names = [c["name"] for c in data["discretionary"]]
        assert "Groceries" in essential_names
        assert "Entertainment" in discretionary_names


# ─── Spending breakdown ────────────────────────────────────────────────


class TestBreakdown:
    """Tests for GET /spending/breakdown."""

    def test_breakdown_empty(self, client, auth_header):
        """Breakdown with no expenses."""
        r = client.get("/spending/breakdown", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["totals"]["grand_total"] == 0
        assert "insights" in data

    def test_breakdown_with_data(self, client, auth_header):
        """Breakdown reflects classified spending."""
        today = date.today().isoformat()
        cat_essential = _create_category(client, auth_header, "Groceries")
        cat_disc = _create_category(client, auth_header, "Entertainment")

        # Auto-classify
        client.post("/spending/auto-classify", headers=auth_header)

        # Create expenses
        _create_expense(client, auth_header, "Food", 100, cat_essential, today)
        _create_expense(client, auth_header, "Movie", 30, cat_disc, today)

        r = client.get("/spending/breakdown", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["totals"]["essential"] == 100.0
        assert data["totals"]["discretionary"] == 30.0
        assert data["totals"]["grand_total"] == 130.0

    def test_breakdown_percentages(self, client, auth_header):
        """Breakdown calculates correct percentages."""
        today = date.today().isoformat()
        cat_e = _create_category(client, auth_header, "Rent")
        cat_d = _create_category(client, auth_header, "Shopping")

        client.post("/spending/auto-classify", headers=auth_header)

        _create_expense(client, auth_header, "Rent", 1000, cat_e, today)
        _create_expense(client, auth_header, "Clothes", 250, cat_d, today)

        r = client.get("/spending/breakdown", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["percentages"]["essential"] == pytest.approx(80.0, abs=0.1)
        assert data["percentages"]["discretionary"] == pytest.approx(20.0, abs=0.1)

    def test_breakdown_date_range(self, client, auth_header):
        """Breakdown respects date range filter."""
        cat_id = _create_category(client, auth_header, "Groceries")
        client.post("/spending/auto-classify", headers=auth_header)

        _create_expense(client, auth_header, "Old", 50, cat_id, "2024-01-15")
        _create_expense(client, auth_header, "New", 75, cat_id, "2024-06-15")

        r = client.get(
            "/spending/breakdown?start_date=2024-06-01&end_date=2024-06-30",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["totals"]["essential"] == 75.0

    def test_breakdown_categories_detail(self, client, auth_header):
        """Breakdown includes per-category details."""
        today = date.today().isoformat()
        cat_id = _create_category(client, auth_header, "Groceries")
        client.post("/spending/auto-classify", headers=auth_header)

        _create_expense(client, auth_header, "Store A", 50, cat_id, today)
        _create_expense(client, auth_header, "Store B", 30, cat_id, today)

        r = client.get("/spending/breakdown", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        ess_cats = data["categories"]["essential"]
        assert len(ess_cats) == 1
        assert ess_cats[0]["name"] == "Groceries"
        assert ess_cats[0]["amount"] == 80.0
        assert ess_cats[0]["count"] == 2

    def test_breakdown_insights(self, client, auth_header):
        """Breakdown generates insights."""
        today = date.today().isoformat()
        cat_e = _create_category(client, auth_header, "Rent")
        cat_d = _create_category(client, auth_header, "Entertainment")
        client.post("/spending/auto-classify", headers=auth_header)

        _create_expense(client, auth_header, "Rent", 1500, cat_e, today)
        _create_expense(client, auth_header, "Fun", 300, cat_d, today)

        r = client.get("/spending/breakdown", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["insights"]) > 0


# ─── Spending trend ────────────────────────────────────────────────────


class TestTrend:
    """Tests for GET /spending/trend."""

    def test_trend_empty(self, client, auth_header):
        """Trend with no data."""
        r = client.get("/spending/trend?months=3", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["trend"]) == 3

    def test_trend_structure(self, client, auth_header):
        """Trend entries have expected fields."""
        r = client.get("/spending/trend?months=1", headers=auth_header)
        assert r.status_code == 200
        trend = r.get_json()["trend"]
        assert len(trend) == 1
        entry = trend[0]
        assert "month" in entry
        assert "essential" in entry
        assert "discretionary" in entry
        assert "total" in entry
        assert "essential_pct" in entry
        assert "discretionary_pct" in entry

    def test_trend_invalid_months(self, client, auth_header):
        """months > 24 returns 400."""
        r = client.get("/spending/trend?months=30", headers=auth_header)
        assert r.status_code == 400

    def test_trend_invalid_months_zero(self, client, auth_header):
        """months < 1 returns 400."""
        r = client.get("/spending/trend?months=0", headers=auth_header)
        assert r.status_code == 400


# ─── Authentication tests ──────────────────────────────────────────────


class TestSpendingAuth:
    """Tests that endpoints require authentication."""

    def test_auto_classify_requires_auth(self, client):
        r = client.post("/spending/auto-classify")
        assert r.status_code in (401, 422)

    def test_categories_requires_auth(self, client):
        r = client.get("/spending/categories")
        assert r.status_code in (401, 422)

    def test_breakdown_requires_auth(self, client):
        r = client.get("/spending/breakdown")
        assert r.status_code in (401, 422)

    def test_trend_requires_auth(self, client):
        r = client.get("/spending/trend")
        assert r.status_code in (401, 422)
