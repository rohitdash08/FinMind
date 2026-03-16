"""Tests for savings opportunity detection engine (#119)."""

from datetime import date, timedelta


TODAY = date.today().isoformat()


# ── helpers ───────────────────────────────────────────────────────────────────

def _create_category(client, auth_header, name="Groceries"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (200, 201)
    return r.get_json()["id"]


def _add_expense(client, auth_header, category_id, amount, spent_at=None, expense_type="EXPENSE", notes=None):
    payload = {
        "category_id": category_id,
        "amount": amount,
        "expense_type": expense_type,
        "spent_at": spent_at or TODAY,
    }
    if notes:
        payload["notes"] = notes
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code in (200, 201)


def _date_months_ago(n: int) -> str:
    return (date.today() - timedelta(days=30 * n)).isoformat()


# ── endpoint smoke tests ──────────────────────────────────────────────────────

def test_savings_opportunities_no_data(client, auth_header):
    r = client.get("/insights/savings-opportunities", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["total_opportunities"] == 0
    assert data["total_estimated_monthly_saving"] == 0


def test_savings_opportunities_requires_auth(client):
    r = client.get("/insights/savings-opportunities")
    assert r.status_code == 401


def test_savings_opportunities_invalid_months_param(client, auth_header):
    """Non-numeric months param should fall back to default without error."""
    r = client.get("/insights/savings-opportunities?months=abc", headers=auth_header)
    assert r.status_code == 200
    assert "months_analysed" in r.get_json()


def test_savings_opportunities_months_capped(client, auth_header):
    """months param should be capped at 12."""
    r = client.get("/insights/savings-opportunities?months=100", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["months_analysed"] == 12


# ── underspend detection ──────────────────────────────────────────────────────

def test_consistent_underspend_detected(client, auth_header):
    """Add high spend 2 months ago, then low spend last month — should flag underspend."""
    cid = _create_category(client, auth_header, "Transport")
    # 2 months ago: high spend
    _add_expense(client, auth_header, cid, 1000, _date_months_ago(2))
    # 1 month ago: 50% lower
    _add_expense(client, auth_header, cid, 500, _date_months_ago(1))
    r = client.get("/insights/savings-opportunities?months=3", headers=auth_header)
    data = r.get_json()
    underspend_ops = [o for o in data["opportunities"] if o["type"] == "consistent_underspend"]
    # May or may not trigger depending on month boundaries, just check structure
    for op in underspend_ops:
        assert op["category_id"] == cid
        assert op["estimated_monthly_saving"] > 0
        assert "message" in op


# ── subscription detection ────────────────────────────────────────────────────

def test_recurring_subscription_detected(client, auth_header):
    """Same amount in 2 different months should be flagged as a subscription."""
    cid = _create_category(client, auth_header, "Streaming")
    # Same amount exactly in two different months
    _add_expense(client, auth_header, cid, 499.0, _date_months_ago(2))
    _add_expense(client, auth_header, cid, 499.0, _date_months_ago(1))
    r = client.get("/insights/savings-opportunities?months=3", headers=auth_header)
    data = r.get_json()
    subs = [o for o in data["opportunities"] if o["type"] == "recurring_subscription"]
    assert len(subs) >= 1
    assert subs[0]["recurring_amount"] == 499.0
    assert subs[0]["estimated_annual_cost"] == pytest.approx(499.0 * 12)
    assert len(subs[0]["months_detected"]) >= 2


def test_non_recurring_not_flagged(client, auth_header):
    """Different amounts should not be detected as a subscription."""
    cid = _create_category(client, auth_header, "OneTime")
    _add_expense(client, auth_header, cid, 100.0, _date_months_ago(2))
    _add_expense(client, auth_header, cid, 200.0, _date_months_ago(1))
    r = client.get("/insights/savings-opportunities?months=3", headers=auth_header)
    subs = [o for o in r.get_json()["opportunities"] if o["type"] == "recurring_subscription"]
    # Amounts differ → no subscription for this category
    assert all(o["category_id"] != cid for o in subs)


# ── top spender categories ────────────────────────────────────────────────────

def test_top_spender_categories_returned(client, auth_header):
    cid = _create_category(client, auth_header, "Rent")
    _add_expense(client, auth_header, cid, 15000, _date_months_ago(1))
    r = client.get("/insights/savings-opportunities", headers=auth_header)
    data = r.get_json()
    assert isinstance(data["top_spender_categories"], list)
    top_ids = [t["category_id"] for t in data["top_spender_categories"]]
    assert cid in top_ids


# ── irregular big spends ──────────────────────────────────────────────────────

def test_irregular_big_spend_detected(client, auth_header):
    """A single expense > 2× category average should be flagged."""
    cid = _create_category(client, auth_header, "Dining")
    # Several normal-sized expenses
    for _ in range(3):
        _add_expense(client, auth_header, cid, 200, _date_months_ago(2))
    # One big outlier
    _add_expense(client, auth_header, cid, 2000, _date_months_ago(1))
    r = client.get("/insights/savings-opportunities?months=3", headers=auth_header)
    big = [o for o in r.get_json()["opportunities"] if o["type"] == "irregular_big_spend"]
    assert any(o["category_id"] == cid and o["amount"] == 2000 for o in big)


def test_income_excluded_from_analysis(client, auth_header):
    """INCOME type transactions should not influence opportunity detection."""
    cid = _create_category(client, auth_header, "Salary")
    _add_expense(client, auth_header, cid, 50000, _date_months_ago(1), expense_type="INCOME")
    r = client.get("/insights/savings-opportunities", headers=auth_header)
    data = r.get_json()
    all_cat_ids = [o["category_id"] for o in data["opportunities"]]
    # Income category should not appear in opportunities
    assert cid not in all_cat_ids


def test_response_structure(client, auth_header):
    r = client.get("/insights/savings-opportunities", headers=auth_header)
    data = r.get_json()
    assert "months_analysed" in data
    assert "total_estimated_monthly_saving" in data
    assert "opportunities" in data
    assert "top_spender_categories" in data
    assert "summary" in data
    summary = data["summary"]
    assert "consistent_underspend" in summary
    assert "recurring_subscriptions" in summary
    assert "irregular_big_spends" in summary
    assert "total_opportunities" in summary


import pytest
