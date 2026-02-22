"""Tests for the weekly digest feature."""

from datetime import date, timedelta


def _create_category(client, auth_header, name="General"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    cats = [c for c in r.get_json() if c["name"] == name]
    return cats[0]["id"]


def _add_expense(client, auth_header, amount, category_id, expense_date, expense_type="EXPENSE"):
    payload = {
        "amount": amount,
        "currency": "USD",
        "category_id": category_id,
        "description": f"Test {expense_type}",
        "date": str(expense_date),
    }
    if expense_type == "INCOME":
        payload["expense_type"] = "INCOME"
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201, f"Failed to create expense: {r.get_json()}"
    return r.get_json()


def test_weekly_digest_empty(client, auth_header):
    """Digest with no expenses returns zero totals."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "period" in data
    assert "totals" in data
    assert "highlights" in data
    assert data["totals"]["income"] == 0
    assert data["totals"]["expenses"] == 0
    assert data["totals"]["net"] == 0
    assert data["category_breakdown"] == []
    assert data["daily_spending"] == []


def test_weekly_digest_with_expenses(client, auth_header):
    """Digest correctly summarizes expenses for the current week."""
    cat_id = _create_category(client, auth_header, "Food")

    # Add expenses for today (current week)
    today = date.today()
    _add_expense(client, auth_header, 25.50, cat_id, today)
    _add_expense(client, auth_header, 15.00, cat_id, today)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["totals"]["expenses"] == 40.50
    assert len(data["category_breakdown"]) == 1
    assert data["category_breakdown"][0]["category"] == "Food"
    assert data["category_breakdown"][0]["total"] == 40.50
    assert data["category_breakdown"][0]["count"] == 2


def test_weekly_digest_with_date_param(client, auth_header):
    """Digest respects the date query parameter."""
    cat_id = _create_category(client, auth_header, "Transport")

    # Add expense for a specific past date
    past_date = date(2026, 1, 15)  # a Wednesday
    _add_expense(client, auth_header, 100.00, cat_id, past_date)

    r = client.get(f"/digest/weekly?date={past_date}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["totals"]["expenses"] == 100.00
    assert data["period"]["start"] == "2026-01-12"  # Monday of that week
    assert data["period"]["end"] == "2026-01-18"  # Sunday


def test_weekly_digest_comparison(client, auth_header):
    """Digest includes comparison with previous week."""
    cat_id = _create_category(client, auth_header, "Shopping")

    today = date.today()
    week_ago = today - timedelta(days=7)

    # Previous week expense
    _add_expense(client, auth_header, 200.00, cat_id, week_ago)
    # Current week expense
    _add_expense(client, auth_header, 50.00, cat_id, today)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["comparison"]["previous_week_expenses"] == 200.00
    assert data["comparison"]["change"] == -150.00
    assert data["comparison"]["change_percent"] is not None


def test_weekly_digest_unauthorized(client):
    """Digest endpoint requires authentication."""
    r = client.get("/digest/weekly")
    assert r.status_code in (401, 422)
