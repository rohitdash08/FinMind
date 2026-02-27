"""Tests for weekly digest functionality."""

from datetime import date, timedelta


def _get_monday(d: date) -> date:
    """Get the Monday of the week containing the given date."""
    return d - timedelta(days=d.weekday())


def test_weekly_digest_returns_complete_structure(client, auth_header):
    """Test that weekly digest returns all expected fields."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Check top-level structure
    assert "period" in payload
    assert "summary" in payload
    assert "trends" in payload
    assert "category_breakdown" in payload
    assert "daily_breakdown" in payload
    assert "upcoming_bills" in payload
    assert "top_transactions" in payload
    assert "insights" in payload
    assert "meta" in payload
    
    # Check period structure
    assert "week_start" in payload["period"]
    assert "week_end" in payload["period"]
    assert "week_number" in payload["period"]
    assert "year" in payload["period"]
    
    # Check summary structure
    assert "total_income" in payload["summary"]
    assert "total_expenses" in payload["summary"]
    assert "net_flow" in payload["summary"]
    assert "transaction_count" in payload["summary"]
    
    # Check trends structure
    assert "expense_change_pct" in payload["trends"]
    assert "income_change_pct" in payload["trends"]
    assert "expense_trend" in payload["trends"]
    
    # Check daily breakdown has 7 days
    assert len(payload["daily_breakdown"]) == 7


def test_weekly_digest_with_transactions(client, auth_header):
    """Test weekly digest with actual transaction data."""
    today = date.today()
    monday = _get_monday(today)
    
    # Create category
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]
    
    # Add income this week
    r = client.post(
        "/expenses",
        json={
            "amount": 2000,
            "description": "Weekly Pay",
            "date": monday.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Add expenses this week
    r = client.post(
        "/expenses",
        json={
            "amount": 150,
            "description": "Groceries",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Coffee",
            "date": (monday + timedelta(days=1)).isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Get digest
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Verify summary
    assert payload["summary"]["total_income"] == 2000.0
    assert payload["summary"]["total_expenses"] == 200.0
    assert payload["summary"]["net_flow"] == 1800.0
    assert payload["summary"]["transaction_count"] == 2  # Only expenses counted
    
    # Verify category breakdown
    assert len(payload["category_breakdown"]) >= 1
    food_cat = next(
        (c for c in payload["category_breakdown"] if c["category_name"] == "Food"),
        None,
    )
    assert food_cat is not None
    assert food_cat["amount"] == 200.0
    assert food_cat["transaction_count"] == 2
    
    # Verify top transactions
    assert len(payload["top_transactions"]) >= 1
    assert payload["top_transactions"][0]["amount"] == 150.0


def test_weekly_digest_week_parameter(client, auth_header):
    """Test weekly digest with specific week parameter."""
    today = date.today()
    last_week_monday = _get_monday(today) - timedelta(days=7)
    
    # Add expense last week
    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Last Week Expense",
            "date": last_week_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Get last week's digest
    r = client.get(
        f"/digest/weekly?week={last_week_monday.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    
    assert payload["period"]["week_start"] == last_week_monday.isoformat()
    assert payload["summary"]["total_expenses"] == 500.0


def test_weekly_digest_invalid_week_format(client, auth_header):
    """Test weekly digest with invalid week format."""
    r = client.get("/digest/weekly?week=invalid", headers=auth_header)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_weekly_digest_normalizes_to_monday(client, auth_header):
    """Test that week parameter is normalized to Monday."""
    today = date.today()
    monday = _get_monday(today)
    wednesday = monday + timedelta(days=2)
    
    # Request using Wednesday
    r = client.get(
        f"/digest/weekly?week={wednesday.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    
    # Should be normalized to Monday
    assert payload["period"]["week_start"] == monday.isoformat()


def test_weekly_digest_trends(client, auth_header):
    """Test week-over-week trend calculations."""
    today = date.today()
    this_monday = _get_monday(today)
    last_monday = this_monday - timedelta(days=7)
    
    # Add expense last week (100)
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Last Week",
            "date": last_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Add expense this week (150) - 50% increase
    r = client.post(
        "/expenses",
        json={
            "amount": 150,
            "description": "This Week",
            "date": this_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Get this week's digest
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # 50% increase from 100 to 150
    assert payload["trends"]["expense_change_pct"] == 50.0
    assert payload["trends"]["previous_week_expenses"] == 100.0
    assert payload["trends"]["expense_trend"] == "increasing"


def test_weekly_digest_with_bills(client, auth_header):
    """Test weekly digest includes upcoming bills."""
    today = date.today()
    monday = _get_monday(today)
    bill_due = monday + timedelta(days=3)  # Due Wednesday of this week
    
    # Create bill due this week
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 79.99,
            "next_due_date": bill_due.isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Get digest
    r = client.get(
        f"/digest/weekly?week={monday.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    
    # Verify bill appears in upcoming_bills
    assert payload["upcoming_bills"]["count"] >= 1
    assert payload["upcoming_bills"]["total"] >= 79.99
    
    bill = next(
        (b for b in payload["upcoming_bills"]["items"] if b["name"] == "Internet"),
        None,
    )
    assert bill is not None
    assert bill["amount"] == 79.99


def test_weekly_summary_endpoint(client, auth_header):
    """Test the condensed weekly summary endpoint."""
    today = date.today()
    monday = _get_monday(today)
    
    # Add some data
    r = client.post(
        "/expenses",
        json={
            "amount": 300,
            "description": "Test Expense",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Get summary
    r = client.get("/digest/weekly/summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Summary should have fewer fields
    assert "period" in payload
    assert "summary" in payload
    assert "trends" in payload
    assert "highlight" in payload
    
    # Should not have detailed breakdowns
    assert "category_breakdown" not in payload
    assert "daily_breakdown" not in payload
    assert "top_transactions" not in payload


def test_weekly_digest_insights_generated(client, auth_header):
    """Test that insights are generated (heuristic when no API key)."""
    today = date.today()
    monday = _get_monday(today)
    
    # Add some expenses
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Big Purchase",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Check insights structure
    assert "insights" in payload
    assert payload["meta"]["method"] == "heuristic"
    
    # Should have insight fields
    insights = payload["insights"]
    assert "insights" in insights or "highlight" in insights or "suggestion" in insights


def test_weekly_digest_daily_breakdown_structure(client, auth_header):
    """Test daily breakdown has correct structure."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    daily = payload["daily_breakdown"]
    assert len(daily) == 7
    
    # Check each day has required fields
    for day in daily:
        assert "date" in day
        assert "day_name" in day
        assert "amount" in day
        assert "transaction_count" in day
    
    # Check day names are correct
    day_names = [d["day_name"] for d in daily]
    assert day_names == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def test_weekly_digest_empty_week(client, auth_header):
    """Test digest for a week with no transactions."""
    # Use a week far in the past
    empty_week = date(2020, 1, 6)  # A Monday
    
    r = client.get(
        f"/digest/weekly?week={empty_week.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    
    assert payload["summary"]["total_income"] == 0.0
    assert payload["summary"]["total_expenses"] == 0.0
    assert payload["summary"]["net_flow"] == 0.0
    assert payload["summary"]["transaction_count"] == 0
    assert len(payload["category_breakdown"]) == 0
    assert len(payload["top_transactions"]) == 0
