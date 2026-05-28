"""
Tests for the weekly smart digest endpoint and service.
"""

import json
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock


@pytest.fixture
def sample_user(client):
    """Register and return a test user."""
    resp = client.post("/auth/register", json={
        "email": "digest@test.com",
        "password": "secret123",
    })
    assert resp.status_code == 201
    body = json.loads(resp.data)
    return body.get("access_token")


@pytest.fixture
def auth_headers(sample_user):
    """Return Authorization headers for the test user."""
    return {"Authorization": f"Bearer {sample_user}"}


def _create_expense(client, auth_headers, **overrides):
    """Helper to create an expense."""
    payload = {
        "description": "Test expense",
        "amount": 100.0,
        "date": date.today().isoformat(),
        "expense_type": "EXPENSE",
    }
    payload.update(overrides)
    resp = client.post("/expenses", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    return json.loads(resp.data)


def test_weekly_digest_returns_200(client, auth_headers):
    """Digest endpoint returns a valid weekly digest."""
    _create_expense(client, auth_headers, amount=50.0, description="Groceries")
    _create_expense(client, auth_headers, amount=30.0, description="Transport")

    resp = client.get("/digest/weekly", headers=auth_headers)
    assert resp.status_code == 200
    body = json.loads(resp.data)

    assert "period" in body
    assert "summary" in body
    assert "comparison" in body
    assert "categories" in body
    assert "daily_spending" in body
    assert "upcoming_bills" in body
    assert "ai_insights" in body
    assert "method" in body

    period = body["period"]
    assert "start" in period
    assert "end" in period
    assert "label" in period

    summary = body["summary"]
    assert summary["expenses"] >= 0
    assert summary["income"] >= 0
    assert isinstance(summary["net_flow"], (int, float))

    trends = body["comparison"]["trends"]
    assert "week_over_week_change_pct" in trends
    assert trends["spending_direction"] in ("up", "down", "stable")


def test_digest_with_custom_date(client, auth_headers):
    """Digest endpoint accepts a custom reference date."""
    _create_expense(client, auth_headers, amount=25.0, description="Coffee")
    custom_date = date.today().isoformat()
    resp = client.get(f"/digest/weekly?date={custom_date}", headers=auth_headers)
    assert resp.status_code == 200


def test_digest_invalid_date_returns_400(client, auth_headers):
    """Digest endpoint returns 400 for invalid date format."""
    resp = client.get("/digest/weekly?date=not-a-date", headers=auth_headers)
    assert resp.status_code == 400


def test_digest_requires_auth(client):
    """Digest endpoint requires authentication."""
    resp = client.get("/digest/weekly")
    assert resp.status_code in (401, 422)


def test_digest_includes_income(client, auth_headers):
    """Digest separates income and expenses correctly."""
    _create_expense(client, auth_headers, amount=200.0, expense_type="INCOME", description="Salary")
    _create_expense(client, auth_headers, amount=75.0, description="Food")

    resp = client.get("/digest/weekly", headers=auth_headers)
    assert resp.status_code == 200
    body = json.loads(resp.data)

    assert body["summary"]["income"] == 200.0
    assert body["summary"]["expenses"] == 75.0
    assert body["summary"]["net_flow"] == 125.0


def test_digest_category_breakdown(client, auth_headers):
    """Digest includes category breakdown."""
    _create_expense(client, auth_headers, amount=40.0, description="Groceries")
    _create_expense(client, auth_headers, amount=60.0, description="Transport")

    resp = client.get("/digest/weekly", headers=auth_headers)
    body = json.loads(resp.data)
    assert resp.status_code == 200
    assert isinstance(body["categories"], list)


def test_digest_daily_spending(client, auth_headers):
    """Digest returns 7 daily spending entries."""
    _create_expense(client, auth_headers, amount=10.0, description="Snack")

    resp = client.get("/digest/weekly", headers=auth_headers)
    body = json.loads(resp.data)
    assert len(body["daily_spending"]) == 7
    assert all("date" in d and "amount" in d for d in body["daily_spending"])


def test_week_range():
    """_week_range returns Monday-Sunday."""
    from app.services.digest import _week_range
    ref = date(2025, 6, 4)
    start, end = _week_range(ref)
    assert start.weekday() == 0  # Monday
    assert end.weekday() == 6    # Sunday
    assert (end - start).days == 6


def test_previous_week_range():
    """_previous_week_range returns 7 days earlier."""
    from app.services.digest import _previous_week_range
    start = date(2025, 6, 2)
    prev_start, prev_end = _previous_week_range(start)
    assert (start - prev_start).days == 7


def test_detect_trends_increased():
    """_detect_trends detects spending increase."""
    from app.services.digest import _detect_trends
    current = {"expenses": 150, "income": 0}
    previous = {"expenses": 100, "income": 0}
    cats = [{"category_name": "Food", "amount": 150, "share_pct": 100}]
    trends = _detect_trends(current, previous, cats)
    assert trends["spending_direction"] == "up"
    assert trends["week_over_week_change_pct"] == 50.0
