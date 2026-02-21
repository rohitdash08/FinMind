"""Tests for household shared budgeting feature."""
import pytest
from app.models_household import Household, HouseholdMember


def test_create_household(client, auth_header):
    """Test creating a new household."""
    response = client.post("/households", 
        json={"name": "Test Family"},
        headers=auth_header
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["household"]["name"] == "Test Family"
    assert data["household"]["role"] == "OWNER"


def test_create_household_no_name(client, auth_header):
    """Test creating household without name fails."""
    response = client.post("/households",
        json={},
        headers=auth_header
    )
    assert response.status_code == 400


def test_get_my_household(client, auth_header):
    """Test getting user's household info."""
    # First create a household
    client.post("/households",
        json={"name": "My Family"},
        headers=auth_header
    )
    
    # Then get it
    response = client.get("/households", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert data["household"]["name"] == "My Family"


def test_get_household_when_none(client, auth_header):
    """Test getting household when user has none."""
    response = client.get("/households", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert data["household"] is None


def test_join_household(client, auth_header, auth_header2, app):
    """Test joining an existing household."""
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "Shared Home"},
        headers=auth_header
    )
    household_id = response1.get_json()["household"]["id"]
    
    # User 2 joins
    response2 = client.post("/households/join",
        json={"household_id": household_id},
        headers=auth_header2
    )
    assert response2.status_code == 200
    assert response2.get_json()["household"]["role"] == "MEMBER"


def test_join_already_in_household(client, auth_header):
    """Test joining when already in a household fails."""
    # Create first household
    client.post("/households",
        json={"name": "First"},
        headers=auth_header
    )
    
    # Try to create another
    response = client.post("/households",
        json={"name": "Second"},
        headers=auth_header
    )
    assert response.status_code == 400


def test_leave_household(client, auth_header):
    """Test leaving a household."""
    # Create household
    client.post("/households",
        json={"name": "To Leave"},
        headers=auth_header
    )
    
    # Leave it
    response = client.post("/households/leave", headers=auth_header)
    assert response.status_code == 200
    
    # Verify left
    response2 = client.get("/households", headers=auth_header)
    assert response2.get_json()["household"] is None


def test_remove_member(client, auth_header, auth_header2, app):
    """Test removing a member from household."""
    from app.extensions import db
    from app.models import User
    
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "Family"},
        headers=auth_header
    )
    household_id = response1.get_json()["household"]["id"]
    
    # User 2 joins
    client.post("/households/join",
        json={"household_id": household_id},
        headers=auth_header2
    )
    
    # Get user 2's ID
    with app.app_context():
        user2 = User.query.filter_by(email="test2@example.com").first()
        user2_id = user2.id
    
    # User 1 removes user 2
    response = client.delete(f"/households/members/{user2_id}", headers=auth_header)
    assert response.status_code == 200
    
    # Verify user 2 is removed
    response2 = client.get("/households", headers=auth_header2)
    assert response2.get_json()["household"] is None
