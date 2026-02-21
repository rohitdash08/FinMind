"""Tests for smart digest feature."""
import pytest
from datetime import datetime, timedelta


def test_get_weekly_digest(client, auth_header):
    """Test getting weekly digest."""
    response = client.get("/digest/weekly", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert "digest" in data
    assert "week_label" in data["digest"]
    assert "summary" in data["digest"]
    assert "total_spent" in data["digest"]["summary"]


def test_weekly_digest_with_expenses(client, auth_header):
    """Test weekly digest with expenses."""
    # Create a category first
    cat_resp = client.post("/categories",
        json={"name": "Food"},
        headers=auth_header
    )
    
    # Add some expenses
    client.post("/expenses",
        json={"amount": 100, "category_id": cat_resp.get_json()["category"]["id"], "notes": "Lunch"},
        headers=auth_header
    )
    client.post("/expenses",
        json={"amount": 50, "notes": "Snack"},
        headers=auth_header
    )
    
    response = client.get("/digest/weekly", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert data["digest"]["summary"]["transaction_count"] >= 2


def test_weekly_digest_specific_week(client, auth_header):
    """Test getting digest for a specific week."""
    response = client.get("/digest/weekly?week=2", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert "week_label" in data["digest"]


def test_weekly_history(client, auth_header):
    """Test getting weekly spending history."""
    response = client.get("/digest/weekly/history?weeks=4", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert "history" in data
    assert len(data["history"]) <= 4


def test_weekly_history_max_weeks(client, auth_header):
    """Test that history is capped at 12 weeks."""
    response = client.get("/digest/weekly/history?weeks=20", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert len(data["history"]) <= 12


def test_trends_analysis(client, auth_header):
    """Test getting spending trends."""
    response = client.get("/digest/trends", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert "trends" in data
    assert "spending_trend" in data["trends"]
    assert "weekly_data" in data["trends"]


def test_insights_generated(client, auth_header):
    """Test that insights are generated in digest."""
    # Add expenses
    client.post("/expenses",
        json={"amount": 200, "notes": "Test"},
        headers=auth_header
    )
    
    response = client.get("/digest/weekly", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert "insights" in data["digest"]
    assert isinstance(data["digest"]["insights"], list)


def test_category_breakdown(client, auth_header):
    """Test category breakdown in digest."""
    # Create categories and expenses
    cat1 = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    cat2 = client.post("/categories", json={"name": "Transport"}, headers=auth_header)
    
    client.post("/expenses",
        json={"amount": 100, "category_id": cat1.get_json()["category"]["id"]},
        headers=auth_header
    )
    client.post("/expenses",
        json={"amount": 50, "category_id": cat2.get_json()["category"]["id"]},
        headers=auth_header
    )
    
    response = client.get("/digest/weekly", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert "category_breakdown" in data["digest"]
    assert len(data["digest"]["category_breakdown"]) >= 2


def test_upcoming_bills_in_digest(client, auth_header):
    """Test that upcoming bills are included in digest."""
    from datetime import date
    
    # Create a bill due soon
    client.post("/bills",
        json={
            "name": "Phone Bill",
            "amount": 50,
            "next_due_date": (date.today() + timedelta(days=3)).isoformat(),
            "cadence": "MONTHLY"
        },
        headers=auth_header
    )
    
    response = client.get("/digest/weekly", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert "upcoming_bills" in data["digest"]
    assert data["digest"]["upcoming_bills"]["count"] >= 1
