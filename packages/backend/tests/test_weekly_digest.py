"""Tests for the weekly financial digest endpoint."""

from datetime import date, timedelta
from unittest.mock import patch


def _register_and_login(client, email="digest-test@example.com"):
    """Helper: register + login, return auth header dict."""
    client.post(
        "/auth/register",
        json={"email": email, "password": "pass1234"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "pass1234"})
    assert r.status_code == 200
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _post_expense(client, headers, amount, spent_at, expense_type="EXPENSE",
                   category_id=None, notes=None):
    """Helper: create an expense."""
    body = {
        "amount": amount,
        "date": spent_at.isoformat(),
        "expense_type": expense_type,
    }
    if category_id:
        body["category_id"] = category_id
    if notes:
        body["notes"] = notes
    r = client.post("/expenses", json=body, headers=headers)
    return r


def test_weekly_digest_empty_week(client):
    """Digest returns zeros when no data exists for the week."""
    headers = _register_and_login(client, email="empty-week@example.com")
    r = client.get("/insights/weekly-digest", headers=headers)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["summary"]["income"] == 0.0
    assert payload["summary"]["expenses"] == 0.0
    assert payload["summary"]["net"] == 0.0
    assert payload["summary"]["transaction_count"] == 0
    assert "insights" in payload
    assert "categories" in payload
    assert "period" in payload


def test_weekly_digest_with_expenses(client):
    """Digest correctly aggregates expenses for the current week."""
    headers = _register_and_login(client, email="expenses-week@example.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # Add expenses on different days of the week
    _post_expense(client, headers, 100, monday, notes="Monday expense")
    _post_expense(client, headers, 50, monday + timedelta(days=2), notes="Wednesday expense")
    _post_expense(client, headers, 25, monday + timedelta(days=4), notes="Friday expense")

    r = client.get("/insights/weekly-digest", headers=headers)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["expenses"] == 175.0
    assert payload["summary"]["transaction_count"] == 3
    assert payload["summary"]["net"] == -175.0


def test_weekly_digest_with_income_and_expenses(client):
    """Digest shows positive net when income > expenses."""
    headers = _register_and_login(client, email="income-week@example.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    _post_expense(client, headers, 500, monday, expense_type="INCOME", notes="Salary")
    _post_expense(client, headers, 100, monday + timedelta(days=1), notes="Groceries")

    r = client.get("/insights/weekly-digest", headers=headers)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["income"] == 500.0
    assert payload["summary"]["expenses"] == 100.0
    assert payload["summary"]["net"] == 400.0


def test_weekly_digest_week_over_week_trend(client):
    """Digest shows correct week-over-week spending change."""
    headers = _register_and_login(client, email="trend-week@example.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # Previous week expenses
    prev_monday = monday - timedelta(days=7)
    _post_expense(client, headers, 200, prev_monday, notes="Last week spend")

    # Current week expenses (50% increase)
    _post_expense(client, headers, 300, monday, notes="This week spend")

    r = client.get("/insights/weekly-digest", headers=headers)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["expenses"] == 300.0
    assert payload["trends"]["previous_week_expenses"] == 200.0
    assert payload["trends"]["spending_wow_change_pct"] == 50.0


def test_weekly_digest_category_breakdown(client):
    """Digest provides accurate category breakdown with percentages."""
    headers = _register_and_login(client, email="cat-week@example.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # Create categories first via the categories endpoint
    r = client.post(
        "/categories",
        json={"name": "Food"},
        headers=headers,
    )
    assert r.status_code in (200, 201)
    food_cat = r.get_json()
    food_id = food_cat.get("id") or food_cat.get("category_id")

    r = client.post(
        "/categories",
        json={"name": "Transport"},
        headers=headers,
    )
    assert r.status_code in (200, 201)
    transport_cat = r.get_json()
    transport_id = transport_cat.get("id") or transport_cat.get("category_id")

    _post_expense(client, headers, 80, monday, category_id=food_id, notes="Food spend")
    _post_expense(client, headers, 20, monday, category_id=transport_id, notes="Transport spend")

    r = client.get("/insights/weekly-digest", headers=headers)
    assert r.status_code == 200
    payload = r.get_json()

    cats = payload["categories"]
    assert len(cats) >= 2

    # Top category should be Food (80)
    food_entry = next((c for c in cats if c["category_name"] == "Food"), None)
    assert food_entry is not None
    assert food_entry["amount"] == 80.0
    assert food_entry["share_pct"] == 80.0


def test_weekly_digest_specific_week_start(client):
    """Digest works with a specific week_start parameter."""
    headers = _register_and_login(client, email="specific-week@example.com")

    # Target a specific week (not current)
    target_monday = date(2026, 3, 2)  # A Monday
    _post_expense(client, headers, 42, target_monday, notes="Target week expense")

    r = client.get(
        f"/insights/weekly-digest?week_start={target_monday.isoformat()}",
        headers=headers,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["summary"]["expenses"] == 42.0
    assert payload["period"]["week_start"] == "2026-03-02"
    assert payload["period"]["week_end"] == "2026-03-08"


def test_weekly_digest_invalid_week_start(client):
    """Digest returns 400 for invalid date format."""
    headers = _register_and_login(client, email="invalid-date@example.com")
    r = client.get(
        "/insights/weekly-digest?week_start=not-a-date",
        headers=headers,
    )
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_weekly_digest_insights_generated(client):
    """Digest generates at least one insight even with minimal data."""
    headers = _register_and_login(client, email="insights-test@example.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    _post_expense(client, headers, 50, monday, notes="Small expense")

    r = client.get("/insights/weekly-digest", headers=headers)
    assert r.status_code == 200
    payload = r.get_json()
    assert len(payload["insights"]) >= 1


def test_weekly_digest_previous_week_zeros(client):
    """When previous week has no data, trends still work correctly."""
    headers = _register_and_login(client, email="prev-zeros@example.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # Only current week data
    _post_expense(client, headers, 150, monday, notes="Current week only")

    r = client.get("/insights/weekly-digest", headers=headers)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["trends"]["previous_week_expenses"] == 0.0
    assert payload["trends"]["spending_wow_change_pct"] == 100.0


def test_weekly_digest_requires_auth(client):
    """Digest returns 401 without authentication."""
    r = client.get("/insights/weekly-digest")
    assert r.status_code == 401
