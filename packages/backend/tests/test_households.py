"""Tests for household shared budgeting feature."""
import pytest
from app.models_household import Household, HouseholdMember, HouseholdRole


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
    assert "invite_code" in data["household"]


def test_create_household_no_name(client, auth_header):
    """Test creating household without name fails."""
    response = client.post("/households",
        json={},
        headers=auth_header
    )
    assert response.status_code == 400
    assert "name is required" in response.get_json()["error"]


def test_create_household_name_too_long(client, auth_header):
    """Test creating household with name too long fails."""
    response = client.post("/households",
        json={"name": "x" * 201},
        headers=auth_header
    )
    assert response.status_code == 400


def test_get_my_household(client, auth_header):
    """Test getting user's household info."""
    # First create a household
    create_response = client.post("/households",
        json={"name": "My Family"},
        headers=auth_header
    )
    assert create_response.status_code == 201
    
    # Then get it
    response = client.get("/households", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert data["household"]["name"] == "My Family"
    assert data["household"]["role"] == "OWNER"
    assert len(data["household"]["members"]) == 1


def test_get_household_when_none(client, auth_header):
    """Test getting household when user has none."""
    response = client.get("/households", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert data["household"] is None


def test_join_household_with_invite_code(client, auth_header, auth_header2):
    """Test joining an existing household using invite code."""
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "Shared Home"},
        headers=auth_header
    )
    assert response1.status_code == 201
    invite_code = response1.get_json()["household"]["invite_code"]
    
    # User 2 joins using invite code
    response2 = client.post("/households/join",
        json={"invite_code": invite_code},
        headers=auth_header2
    )
    assert response2.status_code == 200
    assert response2.get_json()["household"]["role"] == "MEMBER"
    
    # Verify user 2 is in the household
    response3 = client.get("/households", headers=auth_header2)
    assert response3.status_code == 200
    assert response3.get_json()["household"]["name"] == "Shared Home"


def test_join_household_invalid_code(client, auth_header):
    """Test joining with invalid invite code fails."""
    response = client.post("/households/join",
        json={"invite_code": "invalid_code_123"},
        headers=auth_header
    )
    assert response.status_code == 404


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
    assert "already belong" in response.get_json()["error"]


def test_leave_household_as_member(client, auth_header, auth_header2):
    """Test member leaving a household."""
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "To Leave"},
        headers=auth_header
    )
    invite_code = response1.get_json()["household"]["invite_code"]
    
    # User 2 joins
    client.post("/households/join",
        json={"invite_code": invite_code},
        headers=auth_header2
    )
    
    # User 2 leaves
    response = client.post("/households/leave", headers=auth_header2)
    assert response.status_code == 200
    
    # Verify user 2 left
    response2 = client.get("/households", headers=auth_header2)
    assert response2.get_json()["household"] is None


def test_leave_household_as_owner_alone(client, auth_header):
    """Test owner leaving household when alone."""
    # Create household
    client.post("/households",
        json={"name": "To Leave"},
        headers=auth_header
    )
    
    # Leave it
    response = client.post("/households/leave", headers=auth_header)
    assert response.status_code == 200
    
    # Verify household is deleted
    response2 = client.get("/households", headers=auth_header)
    assert response2.get_json()["household"] is None


def test_leave_household_as_owner_with_members(client, auth_header, auth_header2):
    """Test owner cannot leave when there are other members."""
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "Family"},
        headers=auth_header
    )
    invite_code = response1.get_json()["household"]["invite_code"]
    
    # User 2 joins
    client.post("/households/join",
        json={"invite_code": invite_code},
        headers=auth_header2
    )
    
    # User 1 tries to leave
    response = client.post("/households/leave", headers=auth_header)
    assert response.status_code == 400
    assert "Transfer ownership" in response.get_json()["error"]


def test_remove_member(client, auth_header, auth_header2, app):
    """Test removing a member from household."""
    from app.extensions import db
    from app.models import User
    
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "Family"},
        headers=auth_header
    )
    invite_code = response1.get_json()["household"]["invite_code"]
    
    # User 2 joins
    client.post("/households/join",
        json={"invite_code": invite_code},
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


def test_remove_member_insufficient_permission(client, auth_header, auth_header2, app):
    """Test member cannot remove other members."""
    from app.models import User
    
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "Family"},
        headers=auth_header
    )
    invite_code = response1.get_json()["household"]["invite_code"]
    
    # User 2 joins
    client.post("/households/join",
        json={"invite_code": invite_code},
        headers=auth_header2
    )
    
    # Get user 1's ID
    with app.app_context():
        user1 = User.query.filter_by(email="test@example.com").first()
        user1_id = user1.id
    
    # User 2 tries to remove user 1
    response = client.delete(f"/households/members/{user1_id}", headers=auth_header2)
    assert response.status_code == 403


def test_update_member_role(client, auth_header, auth_header2, app):
    """Test updating a member's role."""
    from app.models import User
    
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "Family"},
        headers=auth_header
    )
    invite_code = response1.get_json()["household"]["invite_code"]
    
    # User 2 joins
    client.post("/households/join",
        json={"invite_code": invite_code},
        headers=auth_header2
    )
    
    # Get user 2's ID
    with app.app_context():
        user2 = User.query.filter_by(email="test2@example.com").first()
        user2_id = user2.id
    
    # User 1 promotes user 2 to admin
    response = client.patch(f"/households/members/{user2_id}/role",
        json={"role": "ADMIN"},
        headers=auth_header
    )
    assert response.status_code == 200
    assert response.get_json()["member"]["role"] == "ADMIN"


def test_transfer_ownership(client, auth_header, auth_header2, app):
    """Test transferring household ownership."""
    from app.models import User
    
    # User 1 creates household
    response1 = client.post("/households",
        json={"name": "Family"},
        headers=auth_header
    )
    invite_code = response1.get_json()["household"]["invite_code"]
    
    # User 2 joins
    client.post("/households/join",
        json={"invite_code": invite_code},
        headers=auth_header2
    )
    
    # Get user 2's ID
    with app.app_context():
        user2 = User.query.filter_by(email="test2@example.com").first()
        user2_id = user2.id
    
    # User 1 transfers ownership to user 2
    response = client.post("/households/transfer-ownership",
        json={"user_id": user2_id},
        headers=auth_header
    )
    assert response.status_code == 200
    
    # Verify user 2 is now owner
    response2 = client.get("/households", headers=auth_header2)
    assert response2.get_json()["household"]["role"] == "OWNER"
    
    # Verify user 1 is now admin
    response3 = client.get("/households", headers=auth_header)
    assert response3.get_json()["household"]["role"] == "ADMIN"


def test_regenerate_invite_code(client, auth_header):
    """Test regenerating household invite code."""
    # Create household
    response1 = client.post("/households",
        json={"name": "Family"},
        headers=auth_header
    )
    old_code = response1.get_json()["household"]["invite_code"]
    
    # Regenerate code
    response2 = client.post("/households/invite-code/regenerate", headers=auth_header)
    assert response2.status_code == 200
    new_code = response2.get_json()["invite_code"]
    
    # Verify code changed
    assert new_code != old_code
    
    # Verify old code no longer works
    response3 = client.post("/households/join",
        json={"invite_code": old_code},
        headers=auth_header2
    )
    assert response3.status_code == 404
