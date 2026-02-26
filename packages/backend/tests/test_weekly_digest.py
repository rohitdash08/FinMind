"""Tests for smart digest – weekly financial summary (#121)."""

from datetime import date, timedelta
from decimal import Decimal


def _setup_user(client):
    """Register, login, return (access_token, user_id)."""
    email, pw = "digest@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})
    r = client.post("/auth/login", json={"email": email, "password": pw})
    data = r.get_json()
    # Decode user id from token via /auth/me
    access = data["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    uid = me.get_json()["id"]
    return access, uid


def _add_expense(client, auth, amount, expense_type="EXPENSE", spent_at=None):
    payload = {
        "amount": amount,
        "expense_type": expense_type,
        "notes": "test",
    }
    if spent_at:
        payload["spent_at"] = spent_at
    return client.post("/expenses", json=payload, headers=auth)


def test_weekly_digest_empty(client):
    """Digest with no transactions returns zero totals."""
    access, _ = _setup_user(client)
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/digest/weekly", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_income"] == 0
    assert data["total_expenses"] == 0
    assert data["net_savings"] == 0
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0


def test_weekly_digest_with_transactions(client, app_fixture):
    """Digest correctly sums income and expenses for the current week."""
    access, uid = _setup_user(client)
    auth = {"Authorization": f"Bearer {access}"}

    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # Add expenses and income for this week
    _add_expense(client, auth, 500, "EXPENSE", monday.isoformat())
    _add_expense(client, auth, 300, "EXPENSE", (monday + timedelta(days=1)).isoformat())
    _add_expense(client, auth, 2000, "INCOME", monday.isoformat())

    r = client.get("/digest/weekly", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_expenses"] == 800.0
    assert data["total_income"] == 2000.0
    assert data["net_savings"] == 1200.0


def test_weekly_digest_with_date_param(client):
    """Digest accepts a date query parameter."""
    access, _ = _setup_user(client)
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/digest/weekly?date=2025-01-06", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["week_start"] == "2025-01-06"
    assert data["week_end"] == "2025-01-12"


def test_weekly_digest_invalid_date(client):
    """Invalid date param returns 400."""
    access, _ = _setup_user(client)
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/digest/weekly?date=not-a-date", headers=auth)
    assert r.status_code == 400


def test_weekly_digest_category_breakdown(client, app_fixture):
    """Digest includes category breakdown."""
    access, uid = _setup_user(client)
    auth = {"Authorization": f"Bearer {access}"}

    today = date.today()
    monday = today - timedelta(days=today.weekday())

    _add_expense(client, auth, 100, "EXPENSE", monday.isoformat())

    r = client.get("/digest/weekly", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data["category_breakdown"], list)


def test_weekly_digest_recommendations(client, app_fixture):
    """Digest generates recommendations."""
    access, uid = _setup_user(client)
    auth = {"Authorization": f"Bearer {access}"}

    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # Spend more than income
    _add_expense(client, auth, 5000, "EXPENSE", monday.isoformat())
    _add_expense(client, auth, 1000, "INCOME", monday.isoformat())

    r = client.get("/digest/weekly", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    recs = data["recommendations"]
    assert any("exceeded" in r.lower() for r in recs)


def test_weekly_digest_trend(client, app_fixture):
    """Digest calculates week-over-week trend when previous data exists."""
    access, uid = _setup_user(client)
    auth = {"Authorization": f"Bearer {access}"}

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    prev_monday = monday - timedelta(days=7)

    # Previous week
    _add_expense(client, auth, 1000, "EXPENSE", prev_monday.isoformat())
    # Current week — double
    _add_expense(client, auth, 2000, "EXPENSE", monday.isoformat())

    r = client.get("/digest/weekly", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["expense_trend_pct"] is not None
    assert data["expense_trend_pct"] == 100.0  # doubled
