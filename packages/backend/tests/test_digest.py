from datetime import date, timedelta


def test_weekly_digest_empty(client, auth_header):
    """Digest works even with no data."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "summary" in data
    assert "vs_previous_week" in data
    assert "top_categories" in data
    assert "daily_breakdown" in data
    assert "upcoming_bills" in data
    assert "insights" in data
    assert data["summary"]["total_income"] == 0
    assert data["summary"]["total_spending"] == 0
    assert data["summary"]["net_flow"] == 0
    assert data["summary"]["transaction_count"] == 0
    assert len(data["daily_breakdown"]) == 7


def test_weekly_digest_with_data(client, auth_header):
    """Digest correctly aggregates expenses and income."""
    today = date.today()

    # Add some expenses this week
    client.post("/expenses", json={
        "amount": 50.00,
        "expense_type": "EXPENSE",
        "notes": "Groceries",
        "spent_at": today.isoformat(),
    }, headers=auth_header)

    client.post("/expenses", json={
        "amount": 30.00,
        "expense_type": "EXPENSE",
        "notes": "Gas",
        "spent_at": today.isoformat(),
    }, headers=auth_header)

    client.post("/expenses", json={
        "amount": 500.00,
        "expense_type": "INCOME",
        "notes": "Freelance payment",
        "spent_at": today.isoformat(),
    }, headers=auth_header)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["summary"]["total_spending"] == 80.00
    assert data["summary"]["total_income"] == 500.00
    assert data["summary"]["net_flow"] == 420.00
    assert data["summary"]["transaction_count"] == 3


def test_weekly_digest_with_custom_date(client, auth_header):
    """Digest accepts custom end_date parameter."""
    r = client.get("/digest/weekly?end_date=2026-04-06", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["period"]["end"] == "2026-04-06"
    assert data["period"]["start"] == "2026-03-31"


def test_weekly_digest_invalid_date(client, auth_header):
    """Digest rejects invalid date format."""
    r = client.get("/digest/weekly?end_date=not-a-date", headers=auth_header)
    assert r.status_code == 400


def test_weekly_digest_insights(client, auth_header):
    """Digest generates meaningful insights."""
    today = date.today()

    # Add significant spending
    client.post("/expenses", json={
        "amount": 200.00,
        "expense_type": "EXPENSE",
        "notes": "Big purchase",
        "spent_at": today.isoformat(),
    }, headers=auth_header)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    # Should have at least one insight (net negative, biggest day, etc.)
    assert len(data["insights"]) >= 1
    # Each insight has required fields
    for insight in data["insights"]:
        assert "type" in insight
        assert "title" in insight
        assert "message" in insight
        assert insight["type"] in ("positive", "warning", "info", "reminder")


def test_weekly_digest_previous_week_comparison(client, auth_header):
    """Digest compares with previous week."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    vs = data["vs_previous_week"]
    assert "income_change_pct" in vs
    assert "spending_change_pct" in vs
    assert "income_trend" in vs
    assert "spending_trend" in vs
    assert vs["income_trend"] in ("up", "down", "flat")
    assert vs["spending_trend"] in ("up", "down", "flat")


def test_send_digest_endpoint(client, auth_header):
    """Send digest endpoint responds (may fail without SMTP config)."""
    r = client.post("/digest/weekly/send", headers=auth_header)
    # Either sent or failed (depends on SMTP config in test env)
    assert r.status_code in (200, 500)
    data = r.get_json()
    assert "status" in data
