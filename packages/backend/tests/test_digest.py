from datetime import date, timedelta
import pytest


def test_weekly_digest_requires_auth(client):
    """Test that the digest endpoint requires authentication."""
    r = client.get("/api/digest/weekly")
    assert r.status_code == 401


def test_weekly_digest_default_4_weeks(client, auth_header):
    """Test that default view is 4 weeks."""
    r = client.get("/api/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["period"]["weeks"] == 4
    assert "weeks" in data
    assert "top_categories" in data
    assert "upcoming_bills" in data


def test_weekly_digest_custom_weeks(client, auth_header):
    """Test configurable 4/8/12 week views."""
    for weeks in [4, 8, 12]:
        r = client.get(f"/api/digest/weekly?weeks={weeks}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["period"]["weeks"] == weeks


def test_weekly_digest_with_expenses(client, auth_header):
    """Test WoW delta computation with expense data."""
    # Create a category first
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    today = date.today()
    # Add expenses for current week and previous week
    for i in range(7):
        day = today - timedelta(days=i)
        r = client.post(
            "/expenses",
            json={
                "amount": 10.0,
                "description": f"Food expense {i}",
                "category_id": cat_id,
                "date": day.isoformat(),
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get("/api/digest/weekly?weeks=4", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    # Should have at least one week with data
    assert len(data["weeks"]) > 0
    current_week = data["weeks"][0]
    assert current_week["total"] > 0
    # Current week should have trend (first week has no delta)
    assert current_week["trend"] in ["up", "down", "flat"]


def test_weekly_digest_category_sorting(client, auth_header):
    """Test that categories are sorted by amount and limited to top 5."""
    # Create multiple categories
    cat_ids = []
    for name in ["Food", "Transport", "Entertainment", "Shopping", "Health", "Other"]:
        r = client.post("/categories", json={"name": name}, headers=auth_header)
        assert r.status_code == 201
        cat_ids.append(r.get_json()["id"])

    # Add expenses with different amounts
    today = date.today()
    amounts = [100.0, 50.0, 30.0, 20.0, 10.0, 5.0]
    for cat_id, amount in zip(cat_ids, amounts):
        r = client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": f"Expense in category",
                "category_id": cat_id,
                "date": today.isoformat(),
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get("/api/digest/weekly?weeks=4", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    # Check top categories - should be limited to 5
    assert len(data["top_categories"]) <= 5
    # Should be sorted by amount descending
    if len(data["top_categories"]) > 1:
        for i in range(len(data["top_categories"]) - 1):
            assert data["top_categories"][i]["amount"] >= data["top_categories"][i + 1]["amount"]


def test_weekly_digest_upcoming_bills(client, auth_header):
    """Test upcoming bills (next 7 days) are included."""
    from datetime import date, timedelta
    
    today = date.today()
    
    # Create a bill due in 3 days
    r = client.post(
        "/bills",
        json={
            "name": "Internet Bill",
            "amount": 50.0,
            "currency": "USD",
            "next_due_date": (today + timedelta(days=3)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/api/digest/weekly?weeks=4", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    # Should have the upcoming bill
    assert len(data["upcoming_bills"]) >= 1
    bill = data["upcoming_bills"][0]
    assert bill["name"] == "Internet Bill"


def test_weekly_digest_empty_state(client, auth_header):
    """Test edge case with no expenses or bills."""
    r = client.get("/api/digest/weekly?weeks=4", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    assert data["weeks"] == []
    assert data["top_categories"] == []
    assert data["upcoming_bills"] == []
    assert data["summary"]["current_week_total"] == 0