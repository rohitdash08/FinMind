"""Tests for the savings opportunity detection engine."""

from datetime import date, timedelta


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def _create_expense(client, auth_header, amount, description, spent_at, category_id=None):
    payload = {
        "amount": amount,
        "description": description,
        "date": spent_at if isinstance(spent_at, str) else spent_at.isoformat(),
        "expense_type": "EXPENSE",
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


class TestSavingsOpportunitiesEndpoint:
    def test_returns_empty_when_no_expenses(self, client, auth_header):
        r = client.get("/insights/savings-opportunities", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["opportunities"] == []
        assert "month" in payload

    def test_accepts_month_param(self, client, auth_header):
        r = client.get(
            "/insights/savings-opportunities?month=2025-06", headers=auth_header
        )
        assert r.status_code == 200
        assert r.get_json()["month"] == "2025-06"

    def test_requires_auth(self, client):
        r = client.get("/insights/savings-opportunities")
        assert r.status_code == 401


class TestMonthOverMonthIncrease:
    def test_detects_spending_spike(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Dining")

        current = date.today().replace(day=10)
        py, pm = (current.year, current.month - 1) if current.month > 1 else (current.year - 1, 12)
        previous = date(py, pm, 10)

        # Previous month: $100
        _create_expense(client, auth_header, 100, "Dinner", previous, cat_id)
        # Current month: $150 (50% increase, above 20% threshold)
        _create_expense(client, auth_header, 150, "Dinner", current, cat_id)

        ym = current.strftime("%Y-%m")
        r = client.get(
            f"/insights/savings-opportunities?month={ym}", headers=auth_header
        )
        assert r.status_code == 200
        opps = r.get_json()["opportunities"]
        mom_opps = [o for o in opps if o["type"] == "month_over_month_increase"]
        assert len(mom_opps) >= 1
        assert mom_opps[0]["potential_savings"] == 50.0
        assert mom_opps[0]["category"] == "Dining"
        assert mom_opps[0]["trend"]["change_pct"] == 50.0


class TestHighFrequencySmallPurchases:
    def test_detects_latte_factor(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Coffee")
        current = date.today().replace(day=1)

        # Create 10 small purchases of $5 each = $50 total
        for i in range(10):
            day = min(current.day + i, 28)
            d = current.replace(day=day)
            _create_expense(client, auth_header, 5, f"Coffee #{i}", d, cat_id)

        ym = current.strftime("%Y-%m")
        r = client.get(
            f"/insights/savings-opportunities?month={ym}", headers=auth_header
        )
        assert r.status_code == 200
        opps = r.get_json()["opportunities"]
        latte_opps = [o for o in opps if o["type"] == "high_frequency_small_purchases"]
        assert len(latte_opps) == 1
        assert latte_opps[0]["potential_savings"] == 25.0  # half of $50
        assert latte_opps[0]["trend"]["transaction_count"] == 10


class TestDuplicateSubscriptions:
    def test_detects_duplicate_charges(self, client, auth_header):
        current = date.today().replace(day=5)

        # Same description + amount appearing twice
        _create_expense(client, auth_header, 9.99, "Netflix", current)
        _create_expense(client, auth_header, 9.99, "Netflix", current.replace(day=15))

        ym = current.strftime("%Y-%m")
        r = client.get(
            f"/insights/savings-opportunities?month={ym}", headers=auth_header
        )
        assert r.status_code == 200
        opps = r.get_json()["opportunities"]
        dup_opps = [o for o in opps if o["type"] == "subscription_duplicate"]
        assert len(dup_opps) >= 1
        assert dup_opps[0]["potential_savings"] == 9.99
        assert "Netflix" in dup_opps[0]["title"]


class TestAboveAverageSpending:
    def test_detects_above_average_category(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Shopping")
        current = date.today().replace(day=10)

        # Build 3 months of history at $100/month
        y, m = current.year, current.month
        for _ in range(3):
            if m == 1:
                y, m = y - 1, 12
            else:
                m -= 1
            d = date(y, m, 10)
            _create_expense(client, auth_header, 100, "Shopping trip", d, cat_id)

        # Current month: $200 (2x the average, above 1.3x threshold)
        _create_expense(client, auth_header, 200, "Big shopping", current, cat_id)

        ym = current.strftime("%Y-%m")
        r = client.get(
            f"/insights/savings-opportunities?month={ym}", headers=auth_header
        )
        assert r.status_code == 200
        opps = r.get_json()["opportunities"]
        avg_opps = [o for o in opps if o["type"] == "above_average_spending"]
        assert len(avg_opps) >= 1
        assert avg_opps[0]["category"] == "Shopping"
        assert avg_opps[0]["potential_savings"] == 100.0


class TestOpportunitiesSortedBySavings:
    def test_sorted_descending(self, client, auth_header):
        cat1 = _create_category(client, auth_header, "Food")
        cat2 = _create_category(client, auth_header, "Transport")

        current = date.today().replace(day=10)
        py, pm = (current.year, current.month - 1) if current.month > 1 else (current.year - 1, 12)
        previous = date(py, pm, 10)

        # Cat1: $100 -> $200 (savings $100)
        _create_expense(client, auth_header, 100, "Food prev", previous, cat1)
        _create_expense(client, auth_header, 200, "Food curr", current, cat1)

        # Cat2: $100 -> $150 (savings $50)
        _create_expense(client, auth_header, 100, "Transport prev", previous, cat2)
        _create_expense(client, auth_header, 150, "Transport curr", current, cat2)

        ym = current.strftime("%Y-%m")
        r = client.get(
            f"/insights/savings-opportunities?month={ym}", headers=auth_header
        )
        assert r.status_code == 200
        opps = r.get_json()["opportunities"]
        savings = [o["potential_savings"] for o in opps]
        assert savings == sorted(savings, reverse=True)
