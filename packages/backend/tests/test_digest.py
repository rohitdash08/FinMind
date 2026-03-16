"""Tests for the weekly digest endpoints."""

from datetime import date, timedelta


def _current_iso_week() -> str:
    y, w, _ = date.today().isocalendar()
    return f"{y}-W{w:02d}"


def _seed_data(client, auth_header):
    """Seed income, expenses, and a bill for the current week."""
    today = date.today()

    # Category
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    # Income
    r = client.post(
        "/expenses",
        json={
            "amount": 5000,
            "description": "Salary",
            "date": today.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Expense
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Groceries",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Bill due this week
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "next_due_date": today.isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201


def test_weekly_digest_empty(client, auth_header):
    """An empty account should still return a valid digest."""
    week = _current_iso_week()
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["week"] == week
    assert payload["summary"]["total_income"] == 0
    assert payload["summary"]["total_expenses"] == 0
    assert payload["summary"]["net_flow"] == 0
    assert payload["summary"]["transaction_count"] == 0
    assert isinstance(payload["category_breakdown"], list)
    assert isinstance(payload["upcoming_bills"], list)
    assert "narrative" in payload


def test_weekly_digest_with_data(client, auth_header):
    """After seeding data, the digest should reflect income and expenses."""
    _seed_data(client, auth_header)
    week = _current_iso_week()
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["total_income"] >= 5000
    assert payload["summary"]["total_expenses"] >= 200
    assert payload["summary"]["net_flow"] >= 4800
    assert payload["summary"]["transaction_count"] >= 2

    # Category breakdown should contain "Food"
    cats = [c["category"] for c in payload["category_breakdown"]]
    assert "Food" in cats

    # Upcoming bills
    bills = [b["name"] for b in payload["upcoming_bills"]]
    assert "Internet" in bills

    # Narrative is a string
    assert isinstance(payload["narrative"], str)
    assert len(payload["narrative"]) > 0


def test_weekly_digest_invalid_week(client, auth_header):
    """Invalid week format should return 400."""
    r = client.get("/digest/weekly?week=bad", headers=auth_header)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_weekly_digest_week_over_week(client, auth_header):
    """Week-over-week change should be 0 when there's no prior week data."""
    _seed_data(client, auth_header)
    week = _current_iso_week()
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["week_over_week_change_pct"] == 0.0


def test_digest_history(client, auth_header):
    """History endpoint should return a list of digests."""
    _seed_data(client, auth_header)
    r = client.get("/digest/weekly/history?count=2", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) == 2
    # First item is current week
    assert data[0]["week"] == _current_iso_week()


def test_digest_requires_auth(client):
    """Digest endpoints require authentication."""
    r = client.get("/digest/weekly")
    assert r.status_code == 401

    r = client.get("/digest/weekly/history")
    assert r.status_code == 401


def test_weekly_digest_caching(client, auth_header):
    """Second request should return cached data."""
    week = _current_iso_week()
    r1 = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r1.status_code == 200
    r2 = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r2.status_code == 200
    assert r1.get_json()["summary"] == r2.get_json()["summary"]
