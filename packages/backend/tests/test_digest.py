"""Tests for the weekly financial digest feature."""

from datetime import date, timedelta


def _seed_expenses(client, auth_header, base_date=None):
    """Seed sample income and expenses for testing."""
    if base_date is None:
        base_date = date.today()

    # Income
    r = client.post(
        "/expenses",
        json={
            "amount": 5000,
            "description": "Salary",
            "date": base_date.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Expenses in various categories
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    r = client.post("/categories", json={"name": "Transport"}, headers=auth_header)
    assert r.status_code == 201
    transport_id = r.get_json()["id"]

    r = client.post(
        "/expenses",
        json={
            "amount": 800,
            "description": "Weekly groceries",
            "date": base_date.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Bus pass",
            "date": base_date.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": transport_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 1500,
            "description": "New headphones",
            "date": (base_date + timedelta(days=1)).isoformat()
            if base_date.weekday() < 6
            else base_date.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    return food_id, transport_id


def test_weekly_digest_returns_comprehensive_data(client, auth_header):
    """The weekly digest should return all expected sections."""
    _seed_expenses(client, auth_header)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    # Top-level keys
    assert "id" in data
    assert "week_start" in data
    assert "week_end" in data
    assert "generated_at" in data
    assert "summary" in data

    summary = data["summary"]
    assert "period" in summary
    assert "overview" in summary
    assert "comparison" in summary
    assert "category_breakdown" in summary
    assert "daily_breakdown" in summary
    assert "trend" in summary
    assert "insights" in summary

    # Overview fields
    overview = summary["overview"]
    assert overview["total_income"] >= 5000
    assert overview["total_expenses"] >= 2500
    assert overview["net_flow"] is not None
    assert overview["transaction_count"] >= 4
    assert overview["avg_daily_spending"] >= 0

    # Category breakdown should be a list
    assert isinstance(summary["category_breakdown"], list)
    assert len(summary["category_breakdown"]) >= 1

    # Daily breakdown should have 7 entries (Mon-Sun)
    assert isinstance(summary["daily_breakdown"], list)
    assert len(summary["daily_breakdown"]) == 7

    # Trend should have 3 weeks
    assert isinstance(summary["trend"], list)
    assert len(summary["trend"]) == 3

    # Insights should be a list
    assert isinstance(summary["insights"], list)


def test_weekly_digest_with_specific_week(client, auth_header):
    """Pass a specific week parameter to generate a digest for that week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    _seed_expenses(client, auth_header, base_date=monday)

    r = client.get(
        f"/digest/weekly?week={monday.isoformat()}", headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["period"]["week_start"] == monday.isoformat()


def test_weekly_digest_invalid_week_param(client, auth_header):
    """Invalid week parameter should return 400."""
    r = client.get("/digest/weekly?week=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert "invalid" in r.get_json()["error"].lower()


def test_weekly_digest_empty_week(client, auth_header):
    """A week with no data should still return a valid (zero) digest."""
    far_past = date(2020, 1, 6)  # a Monday
    r = client.get(
        f"/digest/weekly?week={far_past.isoformat()}", headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    overview = data["summary"]["overview"]
    assert overview["total_income"] == 0
    assert overview["total_expenses"] == 0
    assert overview["net_flow"] == 0
    assert overview["transaction_count"] == 0


def test_weekly_digest_comparison_with_previous_week(client, auth_header):
    """Seed two weeks of data and verify the comparison section."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    prev_monday = monday - timedelta(days=7)

    # Previous week: small expenses
    client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Small expense last week",
            "date": prev_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    # Current week: larger expenses
    client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Big expense this week",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get(
        f"/digest/weekly?week={monday.isoformat()}", headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    comparison = data["summary"]["comparison"]
    assert comparison["prev_week_expenses"] == 100.0
    assert comparison["spending_change_pct"] is not None
    assert comparison["spending_change_pct"] > 0  # spending went up


def test_weekly_digest_savings_rate(client, auth_header):
    """Verify savings rate calculation."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Weekly pay",
            "date": monday.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 600,
            "description": "Spending",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get(
        f"/digest/weekly?week={monday.isoformat()}", headers=auth_header
    )
    assert r.status_code == 200
    overview = r.get_json()["summary"]["overview"]
    # savings_rate = (1000 - 600) / 1000 * 100 = 40%
    assert overview["savings_rate"] == 40.0


def test_biggest_expense_identified(client, auth_header):
    """The biggest expense should be correctly identified."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Coffee",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 9999,
            "description": "Rent payment",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get(
        f"/digest/weekly?week={monday.isoformat()}", headers=auth_header
    )
    assert r.status_code == 200
    biggest = r.get_json()["summary"]["biggest_expense"]
    assert biggest is not None
    assert biggest["description"] == "Rent payment"
    assert biggest["amount"] == 9999.0


def test_digest_history_endpoint(client, auth_header):
    """After generating a digest, it should appear in history."""
    # Generate a digest first
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200

    # Now check history
    r = client.get("/digest/history", headers=auth_header)
    assert r.status_code == 200
    history = r.get_json()
    assert isinstance(history, list)
    assert len(history) >= 1
    assert "week_start" in history[0]
    assert "summary" in history[0]


def test_digest_history_limit(client, auth_header):
    """History should respect the limit parameter."""
    # Generate digest for current week
    client.get("/digest/weekly", headers=auth_header)

    r = client.get("/digest/history?limit=1", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) <= 1


def test_digest_idempotent_regeneration(client, auth_header):
    """Generating a digest for the same week twice should update, not duplicate."""
    r1 = client.get("/digest/weekly", headers=auth_header)
    assert r1.status_code == 200
    id1 = r1.get_json()["id"]

    r2 = client.get("/digest/weekly", headers=auth_header)
    assert r2.status_code == 200
    id2 = r2.get_json()["id"]

    # Same record updated, not a new one
    assert id1 == id2

    # History should show exactly one entry for this week
    r = client.get("/digest/history", headers=auth_header)
    week_starts = [d["week_start"] for d in r.get_json()]
    assert len(set(week_starts)) == len(week_starts)  # no duplicates


def test_digest_requires_auth(client):
    """Endpoints should require authentication."""
    r = client.get("/digest/weekly")
    assert r.status_code == 401

    r = client.get("/digest/history")
    assert r.status_code == 401
