"""Tests for lifestyle inflation detection (issue #118).

Covers:
- Empty data returns stable report
- Rising spending pattern is detected
- Category-level trend analysis
- Insight generation
- API parameter handling
"""

from datetime import date, timedelta

import pytest


def _add_expense(client, auth_header, amount, desc, expense_date):
    resp = client.post(
        "/expenses",
        json={"amount": amount, "description": desc, "date": expense_date},
        headers=auth_header,
    )
    assert resp.status_code == 201
    return resp.get_json()


def test_empty_stable(client, auth_header):
    """No expenses → stable trend."""
    resp = client.get("/lifestyle-inflation", headers=auth_header)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["overall_trend"] == "stable"
    assert data["monthly_growth_rate"] == 0.0


def test_rising_spending_detected(client, auth_header):
    """Increasing monthly spending should be flagged."""
    today = date.today()
    # Create expenses with increasing amounts each month
    for i in range(4):
        month_date = date(today.year, today.month, 1) - timedelta(days=30 * (3 - i))
        amount = 100 + (i * 50)  # 100, 150, 200, 250
        _add_expense(
            client,
            auth_header,
            amount,
            f"Monthly spending {i}",
            month_date.isoformat(),
        )

    resp = client.get("/lifestyle-inflation?months=6", headers=auth_header)
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["overall_trend"] == "rising"
    assert data["monthly_growth_rate"] > 0
    assert len(data["total_spending"]) >= 1


def test_stable_spending(client, auth_header):
    """Consistent spending should show stable trend."""
    today = date.today()
    for i in range(4):
        month_date = date(today.year, today.month, 1) - timedelta(days=30 * (3 - i))
        _add_expense(
            client, auth_header, 100.0, "Groceries", month_date.isoformat()
        )

    resp = client.get("/lifestyle-inflation?months=6", headers=auth_header)
    data = resp.get_json()
    # With same amount each month, growth should be minimal
    assert data["monthly_growth_rate"] <= 5


def test_category_trends_present(client, auth_header):
    """Report should include category-level analysis."""
    today = date.today()
    for i in range(3):
        d = (date(today.year, today.month, 1) - timedelta(days=30 * (2 - i))).isoformat()
        _add_expense(client, auth_header, 50 + i * 20, "Dining", d)

    resp = client.get("/lifestyle-inflation", headers=auth_header)
    data = resp.get_json()
    assert "category_trends" in data


def test_insights_generated(client, auth_header):
    """Rising spending should generate insights."""
    today = date.today()
    for i in range(4):
        d = (date(today.year, today.month, 1) - timedelta(days=30 * (3 - i))).isoformat()
        _add_expense(client, auth_header, 50 * (i + 1), "Lifestyle", d)

    resp = client.get("/lifestyle-inflation", headers=auth_header)
    data = resp.get_json()
    assert "insights" in data
    # With strongly rising spending, should have at least one insight
    if data["monthly_growth_rate"] > 3:
        assert len(data["insights"]) >= 1


def test_months_parameter(client, auth_header):
    """Custom months parameter should work."""
    resp = client.get("/lifestyle-inflation?months=3", headers=auth_header)
    assert resp.status_code == 200

    resp = client.get("/lifestyle-inflation?months=invalid", headers=auth_header)
    assert resp.status_code == 200  # falls back to default

    resp = client.get("/lifestyle-inflation?months=100", headers=auth_header)
    assert resp.status_code == 200  # clamped to max
