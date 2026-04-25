from datetime import date, timedelta
from decimal import Decimal


def _create_goal(client, auth_header, *, name="Test Goal", target_amount=1000, deadline=None):
    payload = {
        "name": name,
        "target_amount": target_amount,
        "currency": "INR",
    }
    if deadline:
        payload["deadline"] = deadline
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def test_create_goal(client, auth_header):
    """Test creating a savings goal."""
    goal = _create_goal(client, auth_header, name="Emergency Fund", target_amount=5000)
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 5000.0
    assert goal["current_amount"] == 0.0
    assert goal["status"] == "active"
    assert goal["currency"] == "INR"


def test_create_goal_with_deadline(client, auth_header):
    """Test creating a goal with a deadline."""
    deadline = (date.today() + timedelta(days=30)).isoformat()
    goal = _create_goal(client, auth_header, name="Vacation", target_amount=2000, deadline=deadline)
    assert goal["deadline"] == deadline


def test_list_goals(client, auth_header):
    """Test listing all savings goals."""
    _create_goal(client, auth_header, name="Goal 1", target_amount=1000)
    _create_goal(client, auth_header, name="Goal 2", target_amount=2000)
    
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    goals = r.get_json()
    assert len(goals) == 2


def test_list_goals_with_status_filter(client, auth_header):
    """Test filtering goals by status."""
    goal = _create_goal(client, auth_header, name="Active Goal", target_amount=1000)
    
    # Filter by active status
    r = client.get("/savings?status=active", headers=auth_header)
    assert r.status_code == 200
    goals = r.get_json()
    assert all(g["status"] == "active" for g in goals)
    
    # Filter by completed status (should be empty)
    r = client.get("/savings?status=completed", headers=auth_header)
    assert r.status_code == 200
    goals = r.get_json()
    assert len(goals) == 0


def test_get_goal(client, auth_header):
    """Test getting a specific goal with progress stats."""
    goal = _create_goal(client, auth_header, name="Get Test", target_amount=1000)
    goal_id = goal["id"]
    
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "Get Test"
    assert "progress" in data
    assert data["progress"]["percent_complete"] == 0.0


def test_get_goal_not_found(client, auth_header):
    """Test getting a non-existent goal returns 404."""
    r = client.get("/savings/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_goal(client, auth_header):
    """Test updating a savings goal."""
    goal = _create_goal(client, auth_header, name="Original Name", target_amount=1000)
    goal_id = goal["id"]
    
    r = client.patch(f"/savings/{goal_id}", json={"name": "Updated Name"}, headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "Updated Name"


def test_delete_goal(client, auth_header):
    """Test deleting a savings goal."""
    goal = _create_goal(client, auth_header, name="To Delete", target_amount=1000)
    goal_id = goal["id"]
    
    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    
    # Verify it's gone
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_create_goal_validation_missing_name(client, auth_header):
    """Test validation: missing name returns 400."""
    r = client.post("/savings", json={"target_amount": 1000}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_goal_validation_missing_target(client, auth_header):
    """Test validation: missing target_amount returns 400."""
    r = client.post("/savings", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400
    assert "target_amount" in r.get_json()["error"]


def test_create_goal_validation_negative_amount(client, auth_header):
    """Test validation: negative target amount returns 400."""
    r = client.post("/savings", json={"name": "Test", "target_amount": -100}, headers=auth_header)
    assert r.status_code == 400


def test_add_contribution(client, auth_header):
    """Test adding a contribution to a goal."""
    goal = _create_goal(client, auth_header, name="Save for Bike", target_amount=1000)
    goal_id = goal["id"]
    
    r = client.post(
        f"/savings/{goal_id}/contributions",
        json={"amount": 250, "notes": "Monthly savings"},
        headers=auth_header,
    )
    assert r.status_code == 201
    contrib = r.get_json()
    assert contrib["amount"] == 250.0
    
    # Verify goal current_amount updated
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    data = r.get_json()
    assert data["current_amount"] == 250.0


def test_add_contribution_invalid_amount(client, auth_header):
    """Test validation: negative contribution amount returns 400."""
    goal = _create_goal(client, auth_header, name="Test", target_amount=1000)
    goal_id = goal["id"]
    
    r = client.post(
        f"/savings/{goal_id}/contributions",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_list_contributions(client, auth_header):
    """Test listing contributions for a goal."""
    goal = _create_goal(client, auth_header, name="Test", target_amount=1000)
    goal_id = goal["id"]
    
    client.post(f"/savings/{goal_id}/contributions", json={"amount": 100}, headers=auth_header)
    client.post(f"/savings/{goal_id}/contributions", json={"amount": 200}, headers=auth_header)
    
    r = client.get(f"/savings/{goal_id}/contributions", headers=auth_header)
    assert r.status_code == 200
    contribs = r.get_json()
    assert len(contribs) == 2


def test_auto_milestone_creation(client, auth_header):
    """Test that 4 auto-milestones are created with each goal."""
    goal = _create_goal(client, auth_header, name="Milestone Test", target_amount=1000)
    goal_id = goal["id"]
    
    r = client.get(f"/savings/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 4
    
    # Check milestone thresholds
    thresholds = [float(m["target_amount"]) for m in milestones]
    assert thresholds == [250.0, 500.0, 750.0, 1000.0]
    
    # Check milestone names
    names = [m["name"] for m in milestones]
    assert "25% - Starting" in names
    assert "50% - Halfway" in names
    assert "75% - Almost There" in names
    assert "100% - Goal Reached" in names


def test_milestone_reached_on_contribution(client, auth_header):
    """Test that milestones are marked as reached when contribution crosses threshold."""
    goal = _create_goal(client, auth_header, name="Reach Milestones", target_amount=1000)
    goal_id = goal["id"]
    
    # Add 250 (25% milestone)
    client.post(f"/savings/{goal_id}/contributions", json={"amount": 250}, headers=auth_header)
    
    r = client.get(f"/savings/{goal_id}/milestones", headers=auth_header)
    milestones = r.get_json()
    
    # First milestone should be reached
    m25 = next(m for m in milestones if "25%" in m["name"])
    assert m25["reached_at"] is not None
    
    # Others should not be reached
    m50 = next(m for m in milestones if "50%" in m["name"])
    assert m50["reached_at"] is None


def test_goal_completion_on_full_contribution(client, auth_header):
    """Test that goal status changes to completed when target is reached."""
    goal = _create_goal(client, auth_header, name="Complete Me", target_amount=500)
    goal_id = goal["id"]
    
    # Add full amount
    client.post(f"/savings/{goal_id}/contributions", json={"amount": 500}, headers=auth_header)
    
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    data = r.get_json()
    assert data["status"] == "completed"
    assert data["current_amount"] == 500.0


def test_mark_goal_completed(client, auth_header):
    """Test manually marking a goal as completed."""
    goal = _create_goal(client, auth_header, name="Manual Complete", target_amount=1000)
    goal_id = goal["id"]
    
    r = client.post(f"/savings/{goal_id}/complete", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "completed"


def test_abandon_goal(client, auth_header):
    """Test abandoning a savings goal."""
    goal = _create_goal(client, auth_header, name="Abandon Me", target_amount=1000)
    goal_id = goal["id"]
    
    r = client.post(f"/savings/{goal_id}/abandon", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "abandoned"


def test_cannot_add_contribution_to_completed_goal(client, auth_header):
    """Test that contributions cannot be added to completed goals."""
    goal = _create_goal(client, auth_header, name="Completed Goal", target_amount=1000)
    goal_id = goal["id"]
    
    # Complete the goal
    client.post(f"/savings/{goal_id}/complete", headers=auth_header)
    
    # Try to add contribution
    r = client.post(f"/savings/{goal_id}/contributions", json={"amount": 100}, headers=auth_header)
    assert r.status_code == 400


def test_goal_progress_calculation(client, auth_header):
    """Test progress calculation with remaining amount and days remaining."""
    deadline = (date.today() + timedelta(days=10)).isoformat()
    goal = _create_goal(client, auth_header, name="Progress Test", target_amount=1000, deadline=deadline)
    goal_id = goal["id"]
    
    # Add 250 (25%)
    client.post(f"/savings/{goal_id}/contributions", json={"amount": 250}, headers=auth_header)
    
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    data = r.get_json()
    progress = data["progress"]
    
    assert progress["percent_complete"] == 25.0
    assert progress["remaining_amount"] == 750.0
    assert progress["days_remaining"] == 10