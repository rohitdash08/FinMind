"""Tests for smart digest API (bounty #121)."""

from datetime import date, timedelta


def test_digest_generate_weekly(client, auth_header):
    """Test generating a weekly digest."""
    r = client.get("/digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "period_start" in data
    assert "period_end" in data
    assert "total_spent" in data
    assert "category_breakdown" in data
    assert "trends" in data
    assert "insights" in data
    assert data["period_type"] == "weekly"


def test_digest_generate_monthly(client, auth_header):
    """Test generating a monthly digest."""
    r = client.get("/digest?period=monthly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["period_type"] == "monthly"


def test_digest_invalid_period(client, auth_header):
    """Test invalid period parameter."""
    r = client.get("/digest?period=yearly", headers=auth_header)
    assert r.status_code == 400


def test_digest_with_expenses(client, auth_header):
    """Test digest includes expenses when present."""
    # Create some expenses first
    today = date.today().isoformat()
    for cat in ["food", "transport", "food"]:
        client.post(
            "/expenses",
            json={
                "amount": 50.0,
                "category": cat,
                "date": today,
                "description": f"Test {cat}",
            },
            headers=auth_header,
        )

    r = client.get("/digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] > 0
    assert "food" in data["category_breakdown"]


def test_digest_history(client, auth_header):
    """Test digest history endpoint."""
    # Generate a digest first
    r = client.get("/digest", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/digest/history", headers=auth_header)
    assert r.status_code == 200
    history = r.get_json()
    assert isinstance(history, list)
    assert len(history) >= 1


def test_digest_history_with_limit(client, auth_header):
    """Test digest history with limit parameter."""
    r = client.get("/digest/history?limit=5", headers=auth_header)
    assert r.status_code == 200


def test_digest_history_filter_period(client, auth_header):
    """Test digest history filtered by period type."""
    r = client.get("/digest/history?period=weekly", headers=auth_header)
    assert r.status_code == 200


def test_digest_force_generate(client, auth_header):
    """Test force generating a digest for a specific date."""
    ref_date = date.today().isoformat()
    r = client.post(
        "/digest/generate",
        json={"period": "weekly", "reference_date": ref_date},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["total_spent"] >= 0


def test_digest_force_generate_invalid_date(client, auth_header):
    """Test force generate with invalid date."""
    r = client.post(
        "/digest/generate",
        json={"period": "weekly", "reference_date": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_digest_force_generate_invalid_period(client, auth_header):
    """Test force generate with invalid period."""
    r = client.post(
        "/digest/generate",
        json={"period": "quarterly"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_digest_trend_detection(client, auth_header):
    """Test that trends are detected when spending changes."""
    today = date.today()
    last_week = today - timedelta(days=7)

    # Create expenses for current period
    for i in range(5):
        client.post(
            "/expenses",
            json={
                "amount": 100.0,
                "category": "food",
                "date": today.isoformat(),
                "description": "Current food",
            },
            headers=auth_header,
        )

    # Create smaller expenses for previous period
    for i in range(2):
        client.post(
            "/expenses",
            json={
                "amount": 50.0,
                "category": "food",
                "date": last_week.isoformat(),
                "description": "Previous food",
            },
            headers=auth_header,
        )

    r = client.get("/digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # Food should show up as a trend (>15% change)
    food_trends = [t for t in data["trends"] if t["category"] == "food"]
    assert len(food_trends) > 0
