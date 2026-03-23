from datetime import date, timedelta


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def test_savings_goals_crud(client, auth_header):
    # Initially empty
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        "name": "Emergency Fund",
        "target_amount": 5000,
        "current_amount": 500,
        "currency": "USD",
        "deadline": (date.today() + timedelta(days=180)).isoformat(),
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 5000.0
    assert goal["current_amount"] == 500.0
    assert goal["progress"] == 10.0
    assert goal["status"] == "ACTIVE"
    assert len(goal["milestones"]) == 4
    assert goal["milestones"][0]["percentage"] == 25
    assert goal["milestones"][0]["reached"] is False
    assert goal["created_at"] is not None  # created_at should be in response

    # Get single goal
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == goal_id

    # List has 1
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Update goal
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"name": "Rainy Day Fund", "current_amount": 1500},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Rainy Day Fund"
    assert updated["current_amount"] == 1500.0
    assert updated["progress"] == 30.0
    assert updated["milestones"][0]["reached"] is True  # 25% reached

    # Delete goal
    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200

    # List is empty again
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


# ---------------------------------------------------------------------------
# Deposit
# ---------------------------------------------------------------------------

def test_savings_goal_deposit(client, auth_header):
    # Create goal
    r = client.post(
        "/savings-goals",
        json={"name": "Vacation", "target_amount": 1000, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Deposit
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 300},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 300.0
    assert r.get_json()["progress"] == 30.0

    # Deposit to complete
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 800},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 1100.0
    assert data["status"] == "COMPLETED"
    assert all(m["reached"] for m in data["milestones"])

    # Cannot deposit to completed goal
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 50},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "not active" in r.get_json()["error"]


def test_deposit_invalid_amounts(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 1000, "currency": "USD"},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Zero amount
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Negative amount
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Non-numeric amount
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": "abc"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Missing amount
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Deposit to non-existent goal
    r = client.post(
        "/savings-goals/99999/deposit",
        json={"amount": 50},
        headers=auth_header,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Withdraw
# ---------------------------------------------------------------------------

def test_savings_goal_withdraw(client, auth_header):
    # Create goal with initial amount
    r = client.post(
        "/savings-goals",
        json={"name": "Travel", "target_amount": 2000, "current_amount": 500, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Withdraw some
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 200},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 300.0

    # Cannot withdraw more than balance
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "insufficient" in r.get_json()["error"]


def test_withdraw_reverts_completed_to_active(client, auth_header):
    # Create and complete a goal
    r = client.post(
        "/savings-goals",
        json={"name": "Done", "target_amount": 100, "current_amount": 100, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]
    assert r.get_json()["status"] == "COMPLETED"

    # Withdraw to go below target
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 50},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "ACTIVE"
    assert r.get_json()["current_amount"] == 50.0


def test_withdraw_from_cancelled_goal_fails(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Cancel Me", "target_amount": 100, "current_amount": 50, "currency": "USD"},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Cancel it
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"status": "CANCELLED"},
        headers=auth_header,
    )
    assert r.status_code == 200

    # Cannot withdraw
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 10},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "cancelled" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# Filter by status
# ---------------------------------------------------------------------------

def test_savings_goal_filter_by_status(client, auth_header):
    # Create two goals
    client.post(
        "/savings-goals",
        json={"name": "Goal A", "target_amount": 100, "currency": "USD"},
        headers=auth_header,
    )
    r = client.post(
        "/savings-goals",
        json={"name": "Goal B", "target_amount": 50, "current_amount": 50, "currency": "USD"},
        headers=auth_header,
    )
    # Goal B should auto-complete on create since current >= target
    assert r.get_json()["status"] == "COMPLETED"

    # Filter active
    r = client.get("/savings-goals?status=ACTIVE", headers=auth_header)
    assert r.status_code == 200
    names = [g["name"] for g in r.get_json()]
    assert "Goal A" in names
    assert "Goal B" not in names

    # Filter completed
    r = client.get("/savings-goals?status=COMPLETED", headers=auth_header)
    assert r.status_code == 200
    names = [g["name"] for g in r.get_json()]
    assert "Goal B" in names
    assert "Goal A" not in names

    # All
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_savings_goal_filter_invalid_status(client, auth_header):
    r = client.get("/savings-goals?status=INVALID", headers=auth_header)
    assert r.status_code == 400
    assert "invalid status" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_savings_goal_validation(client, auth_header):
    # Missing name
    r = client.post(
        "/savings-goals",
        json={"target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]

    # Empty name (whitespace only)
    r = client.post(
        "/savings-goals",
        json={"name": "   ", "target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Name too long
    r = client.post(
        "/savings-goals",
        json={"name": "x" * 201, "target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "200" in r.get_json()["error"]

    # Invalid target_amount (negative)
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid target_amount (zero)
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid target_amount (non-numeric)
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": "abc"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Negative current_amount
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 100, "current_amount": -10},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Not found
    r = client.get("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404

    # Invalid deadline
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 100, "deadline": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid currency
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 100, "currency": "FAKE"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "currency" in r.get_json()["error"]


def test_update_validation(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Valid", "target_amount": 100, "currency": "USD"},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Update with empty name
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"name": ""},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Update with invalid target
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"target_amount": -1},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Update with negative current
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"current_amount": -1},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Update with invalid status
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"status": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Update with invalid currency
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"currency": "FAKE"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Update with invalid deadline
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"deadline": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Clear deadline (null) should work
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"deadline": None},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["deadline"] is None

    # Update non-existent goal
    r = client.patch(
        "/savings-goals/99999",
        json={"name": "Nope"},
        headers=auth_header,
    )
    assert r.status_code == 404

    # Delete non-existent goal
    r = client.delete("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Auto-complete on create
# ---------------------------------------------------------------------------

def test_auto_complete_on_create(client, auth_header):
    """When current_amount >= target_amount at creation, goal is auto-completed."""
    r = client.post(
        "/savings-goals",
        json={"name": "Already Done", "target_amount": 100, "current_amount": 150, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["status"] == "COMPLETED"
    assert r.get_json()["progress"] == 150.0  # 150% progress


def test_auto_complete_on_update(client, auth_header):
    """When updating current_amount to >= target_amount, goal is auto-completed."""
    r = client.post(
        "/savings-goals",
        json={"name": "Growing", "target_amount": 100, "currency": "USD"},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]
    assert r.get_json()["status"] == "ACTIVE"

    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"current_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# Defaults to user currency
# ---------------------------------------------------------------------------

def test_savings_goal_defaults_to_user_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/savings-goals",
        json={"name": "Euro Goal", "target_amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


# ---------------------------------------------------------------------------
# Authorization (user isolation)
# ---------------------------------------------------------------------------

def test_user_cannot_access_other_users_goals(client, auth_header):
    """Goals belong to the authenticated user; another user cannot see/modify them."""
    # Create goal as user 1
    r = client.post(
        "/savings-goals",
        json={"name": "Private Goal", "target_amount": 1000, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Register and login as user 2
    email2 = "user2@example.com"
    password2 = "password456"
    r = client.post("/auth/register", json={"email": email2, "password": password2})
    assert r.status_code in (200, 201)
    r = client.post("/auth/login", json={"email": email2, "password": password2})
    assert r.status_code == 200
    header2 = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    # User 2 should not see user 1's goals
    r = client.get("/savings-goals", headers=header2)
    assert r.status_code == 200
    assert len(r.get_json()) == 0

    # User 2 cannot get user 1's goal
    r = client.get(f"/savings-goals/{goal_id}", headers=header2)
    assert r.status_code == 404

    # User 2 cannot update user 1's goal
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"name": "Hacked"},
        headers=header2,
    )
    assert r.status_code == 404

    # User 2 cannot deposit to user 1's goal
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 100},
        headers=header2,
    )
    assert r.status_code == 404

    # User 2 cannot withdraw from user 1's goal
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 10},
        headers=header2,
    )
    assert r.status_code == 404

    # User 2 cannot delete user 1's goal
    r = client.delete(f"/savings-goals/{goal_id}", headers=header2)
    assert r.status_code == 404

    # Verify user 1's goal is still intact
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Private Goal"


# ---------------------------------------------------------------------------
# Milestones correctness
# ---------------------------------------------------------------------------

def test_milestone_progression(client, auth_header):
    """Verify milestones update correctly as deposits accumulate."""
    r = client.post(
        "/savings-goals",
        json={"name": "Milestone Test", "target_amount": 400, "currency": "USD"},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # 0% - no milestones reached
    data = r.get_json()
    assert all(not m["reached"] for m in data["milestones"])

    # Deposit 100 => 25%
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 100},
        headers=auth_header,
    )
    data = r.get_json()
    assert data["milestones"][0]["reached"] is True   # 25%
    assert data["milestones"][1]["reached"] is False   # 50%

    # Deposit 100 => 50%
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 100},
        headers=auth_header,
    )
    data = r.get_json()
    assert data["milestones"][0]["reached"] is True   # 25%
    assert data["milestones"][1]["reached"] is True    # 50%
    assert data["milestones"][2]["reached"] is False   # 75%

    # Deposit 200 => 100%
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 200},
        headers=auth_header,
    )
    data = r.get_json()
    assert all(m["reached"] for m in data["milestones"])
    assert data["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# Deposit to cancelled goal
# ---------------------------------------------------------------------------

def test_deposit_to_cancelled_goal_fails(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Will Cancel", "target_amount": 100, "currency": "USD"},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Cancel it
    client.patch(
        f"/savings-goals/{goal_id}",
        json={"status": "CANCELLED"},
        headers=auth_header,
    )

    # Cannot deposit
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 10},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "not active" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# No auth
# ---------------------------------------------------------------------------

def test_savings_goals_require_auth(client):
    """All endpoints require authentication."""
    r = client.get("/savings-goals")
    assert r.status_code == 401

    r = client.post("/savings-goals", json={"name": "X", "target_amount": 100})
    assert r.status_code == 401

    r = client.get("/savings-goals/1")
    assert r.status_code == 401

    r = client.patch("/savings-goals/1", json={"name": "Y"})
    assert r.status_code == 401

    r = client.post("/savings-goals/1/deposit", json={"amount": 10})
    assert r.status_code == 401

    r = client.post("/savings-goals/1/withdraw", json={"amount": 10})
    assert r.status_code == 401

    r = client.delete("/savings-goals/1")
    assert r.status_code == 401
