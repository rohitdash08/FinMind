"""Tests for lifestyle inflation detection endpoint."""
import pytest
from datetime import date, timedelta
from decimal import Decimal


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _add_expense(client, headers, amount, category_id, days_ago, expense_type="EXPENSE"):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "category_id": category_id,
            "expense_type": expense_type,
            "spent_at": d,
            "notes": "test",
        },
        headers=headers,
    )
    return r


def _add_category(client, headers, name):
    r = client.post("/categories", json={"name": name}, headers=headers)
    assert r.status_code in (200, 201)
    return r.get_json()["id"]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_lifestyle_inflation_requires_auth(client):
    r = client.get("/insights/lifestyle-inflation")
    assert r.status_code == 401


def test_lifestyle_inflation_empty(client, auth_header):
    r = client.get("/insights/lifestyle-inflation", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["inflated_categories"] == []
    assert data["stable_categories"] == []
    assert data["summary"]["inflated_count"] == 0


def test_lifestyle_inflation_detects_growth(client, auth_header):
    cat_id = _add_category(client, auth_header, "Dining")

    # Previous window: months ~4 and ~5 ago → small spend
    for days in [120, 150]:
        _add_expense(client, auth_header, 100, cat_id, days_ago=days)

    # Recent window: months ~1 and ~2 ago → big spend (inflated)
    for days in [15, 45]:
        _add_expense(client, auth_header, 300, cat_id, days_ago=days)

    r = client.get("/insights/lifestyle-inflation?window_months=2", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # Should detect inflation in Dining
    assert data["summary"]["inflated_count"] >= 1
    names = [c["category_name"] for c in data["inflated_categories"]]
    assert "Dining" in names


def test_lifestyle_inflation_no_growth_stable(client, auth_header):
    cat_id = _add_category(client, auth_header, "Transport")

    # Stable spend across both windows
    for days in [15, 45, 75, 105]:
        _add_expense(client, auth_header, 200, cat_id, days_ago=days)

    r = client.get("/insights/lifestyle-inflation?window_months=2", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # Not inflated (0% change)
    names_inflated = [c["category_name"] for c in data["inflated_categories"]]
    assert "Transport" not in names_inflated


def test_lifestyle_inflation_income_excluded(client, auth_header):
    cat_id = _add_category(client, auth_header, "Salary")

    # Large INCOME entries in recent window
    for days in [15, 45]:
        _add_expense(client, auth_header, 5000, cat_id, days_ago=days, expense_type="INCOME")

    r = client.get("/insights/lifestyle-inflation?window_months=2", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # Income should not appear in inflation results
    for cat in data["inflated_categories"] + data["stable_categories"]:
        assert cat["category_name"] != "Salary"


def test_lifestyle_inflation_response_structure(client, auth_header):
    r = client.get("/insights/lifestyle-inflation", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "inflated_categories" in data
    assert "stable_categories" in data
    assert "summary" in data
    assert "window_months" in data
    assert "inflation_threshold_pct" in data
    summary = data["summary"]
    assert "inflated_count" in summary
    assert "stable_count" in summary
    assert "total_extra_monthly_spend" in summary
    assert "total_extra_annual_spend" in summary


def test_lifestyle_inflation_custom_window(client, auth_header):
    r = client.get("/insights/lifestyle-inflation?window_months=6", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["window_months"] == 6


def test_lifestyle_inflation_custom_threshold(client, auth_header):
    r = client.get(
        "/insights/lifestyle-inflation?threshold_pct=20", headers=auth_header
    )
    assert r.status_code == 200
    assert r.get_json()["inflation_threshold_pct"] == 20.0


def test_lifestyle_inflation_window_capped(client, auth_header):
    # window > 12 should be capped at 12
    r = client.get("/insights/lifestyle-inflation?window_months=99", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["window_months"] == 12


def test_lifestyle_inflation_sorted_by_pct(client, auth_header):
    cat_a = _add_category(client, auth_header, "InflatA")
    cat_b = _add_category(client, auth_header, "InflatB")

    # cat_a: 100 → 300 (+200%)
    for d in [120, 150]:
        _add_expense(client, auth_header, 100, cat_a, days_ago=d)
    for d in [15, 45]:
        _add_expense(client, auth_header, 300, cat_a, days_ago=d)

    # cat_b: 100 → 150 (+50%)
    for d in [120, 150]:
        _add_expense(client, auth_header, 100, cat_b, days_ago=d)
    for d in [15, 45]:
        _add_expense(client, auth_header, 150, cat_b, days_ago=d)

    r = client.get("/insights/lifestyle-inflation?window_months=2", headers=auth_header)
    assert r.status_code == 200
    inflated = r.get_json()["inflated_categories"]
    assert len(inflated) >= 2
    # First item should have higher pct_change
    assert inflated[0]["pct_change"] >= inflated[1]["pct_change"]


def test_lifestyle_inflation_annualised_extra(client, auth_header):
    cat_id = _add_category(client, auth_header, "Shopping")

    for d in [120, 150]:
        _add_expense(client, auth_header, 100, cat_id, days_ago=d)
    for d in [15, 45]:
        _add_expense(client, auth_header, 400, cat_id, days_ago=d)

    r = client.get("/insights/lifestyle-inflation?window_months=2", headers=auth_header)
    assert r.status_code == 200
    inflated = r.get_json()["inflated_categories"]
    found = next((c for c in inflated if c["category_name"] == "Shopping"), None)
    assert found is not None
    # annualised_extra should be 12x abs_change_monthly
    assert abs(found["annualised_extra"] - found["abs_change_monthly"] * 12) < 0.1


def test_lifestyle_inflation_trend_included(client, auth_header):
    cat_id = _add_category(client, auth_header, "Gym")

    for d in [120, 150]:
        _add_expense(client, auth_header, 50, cat_id, days_ago=d)
    for d in [15, 45]:
        _add_expense(client, auth_header, 200, cat_id, days_ago=d)

    r = client.get("/insights/lifestyle-inflation?window_months=2", headers=auth_header)
    assert r.status_code == 200
    inflated = r.get_json()["inflated_categories"]
    found = next((c for c in inflated if c["category_name"] == "Gym"), None)
    assert found is not None
    assert isinstance(found["trend"], list)
    assert len(found["trend"]) == 4  # 2 recent + 2 previous months
    for t in found["trend"]:
        assert "month" in t
        assert "amount" in t


import pytest
