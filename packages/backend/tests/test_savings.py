"""Tests for savings goals feature."""
import pytest
from app.models_savings import SavingsGoal, SavingsMilestone


def test_create_savings_goal(client, auth_header):
    """Test creating a new savings goal."""
    response = client.post("/savings/goals",
        json={
            "name": "Vacation Fund",
            "target_amount": 5000,
            "currency": "USD",
            "deadline": "2026-12-31"
        },
        headers=auth_header
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["goal"]["name"] == "Vacation Fund"
    assert float(data["goal"]["target_amount"]) == 5000


def test_create_goal_no_name(client, auth_header):
    """Test creating goal without name fails."""
    response = client.post("/savings/goals",
        json={"target_amount": 1000},
        headers=auth_header
    )
    assert response.status_code == 400


def test_create_goal_invalid_amount(client, auth_header):
    """Test creating goal with invalid amount fails."""
    response = client.post("/savings/goals",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header
    )
    assert response.status_code == 400


def test_list_savings_goals(client, auth_header):
    """Test listing savings goals."""
    # Create a goal first
    client.post("/savings/goals",
        json={"name": "Emergency Fund", "target_amount": 10000},
        headers=auth_header
    )
    
    response = client.get("/savings/goals", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["goals"]) >= 1


def test_get_single_goal(client, auth_header):
    """Test getting a single goal."""
    # Create a goal
    create_resp = client.post("/savings/goals",
        json={"name": "New Car", "target_amount": 20000},
        headers=auth_header
    )
    goal_id = create_resp.get_json()["goal"]["id"]
    
    response = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert response.status_code == 200
    assert response.get_json()["goal"]["name"] == "New Car"


def test_update_goal_progress(client, auth_header):
    """Test updating goal progress."""
    # Create a goal
    create_resp = client.post("/savings/goals",
        json={"name": "Savings", "target_amount": 100},
        headers=auth_header
    )
    goal_id = create_resp.get_json()["goal"]["id"]
    
    # Update progress
    response = client.put(f"/savings/goals/{goal_id}",
        json={"current_amount": 50},
        headers=auth_header
    )
    assert response.status_code == 200
    assert response.get_json()["goal"]["progress_percentage"] == 50


def test_contribute_to_goal(client, auth_header):
    """Test contributing to a goal."""
    # Create a goal
    create_resp = client.post("/savings/goals",
        json={"name": "Test", "target_amount": 100},
        headers=auth_header
    )
    goal_id = create_resp.get_json()["goal"]["id"]
    
    # Contribute
    response = client.post(f"/savings/goals/{goal_id}/contribute",
        json={"amount": 30},
        headers=auth_header
    )
    assert response.status_code == 200
    assert float(response.get_json()["current_amount"]) == 30


def test_add_milestone(client, auth_header):
    """Test adding a milestone to a goal."""
    # Create a goal
    create_resp = client.post("/savings/goals",
        json={"name": "Test", "target_amount": 1000},
        headers=auth_header
    )
    goal_id = create_resp.get_json()["goal"]["id"]
    
    # Add milestone
    response = client.post(f"/savings/goals/{goal_id}/milestones",
        json={"name": "25% there!", "target_amount": 250},
        headers=auth_header
    )
    assert response.status_code == 201
    assert response.get_json()["milestone"]["name"] == "25% there!"


def test_delete_goal(client, auth_header):
    """Test deleting a goal."""
    # Create a goal
    create_resp = client.post("/savings/goals",
        json={"name": "To Delete", "target_amount": 100},
        headers=auth_header
    )
    goal_id = create_resp.get_json()["goal"]["id"]
    
    # Delete it
    response = client.delete(f"/savings/goals/{goal_id}", headers=auth_header)
    assert response.status_code == 200
    
    # Verify it's gone
    get_resp = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert get_resp.status_code == 404


def test_goal_completion(client, auth_header):
    """Test goal is marked complete when target reached."""
    # Create a goal
    create_resp = client.post("/savings/goals",
        json={"name": "Complete Me", "target_amount": 100},
        headers=auth_header
    )
    goal_id = create_resp.get_json()["goal"]["id"]
    
    # Contribute full amount
    response = client.post(f"/savings/goals/{goal_id}/contribute",
        json={"amount": 100},
        headers=auth_header
    )
    
    # Check goal is complete
    get_resp = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert get_resp.get_json()["goal"]["is_completed"] == True
