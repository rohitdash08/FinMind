from datetime import date, timedelta


def test_savings_goals_crud(client, auth_header):
    # Initially empty
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        "title": "Emergency Fund",
        "target_amount": 10000,
        "current_amount": 2500,
        "deadline": (date.today() + timedelta(days=365)).isoformat(),
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["title"] == "Emergency Fund"
    assert goal["target_amount"] == 10000.0
    assert goal["current_amount"] == 2500.0
    assert goal["status"] in ("ON_TRACK", "BEHIND", "AHEAD")
    assert goal["monthly_target"] is not None

    # List has 1
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Get single
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == goal_id

    # Update
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"current_amount": 5000, "title": "Emergency Savings"},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["current_amount"] == 5000.0
    assert updated["title"] == "Emergency Savings"

    # Delete
    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # Confirm deleted
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_goal_validation(client, auth_header):
    # Missing title
    r = client.post(
        "/savings-goals",
        json={"target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "title" in r.get_json()["error"]

    # Invalid target
    r = client.post(
        "/savings-goals",
        json={"title": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "target_amount" in r.get_json()["error"]

    # Invalid deadline
    r = client.post(
        "/savings-goals",
        json={"title": "Test", "target_amount": 1000, "deadline": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "deadline" in r.get_json()["error"]


def test_savings_goal_not_found(client, auth_header):
    r = client.get("/savings-goals/9999", headers=auth_header)
    assert r.status_code == 404

    r = client.patch(
        "/savings-goals/9999", json={"title": "X"}, headers=auth_header
    )
    assert r.status_code == 404

    r = client.delete("/savings-goals/9999", headers=auth_header)
    assert r.status_code == 404


def test_savings_goal_completed_status(client, auth_header):
    payload = {
        "title": "Small Goal",
        "target_amount": 100,
        "current_amount": 100,
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["status"] == "COMPLETED"


def test_savings_goal_no_deadline(client, auth_header):
    payload = {
        "title": "Open Goal",
        "target_amount": 5000,
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["deadline"] is None
    assert goal["monthly_target"] is None
    assert goal["status"] == "ON_TRACK"


def test_milestones_crud(client, auth_header):
    # Create a goal first
    r = client.post(
        "/savings-goals",
        json={
            "title": "Vacation",
            "target_amount": 5000,
            "current_amount": 1000,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Create milestone (not yet reached)
    r = client.post(
        f"/savings-goals/{goal_id}/milestones",
        json={"title": "25% saved", "amount": 1250},
        headers=auth_header,
    )
    assert r.status_code == 201
    milestone = r.get_json()
    assert milestone["title"] == "25% saved"
    assert milestone["reached_at"] is None

    # Create milestone (already reached)
    r = client.post(
        f"/savings-goals/{goal_id}/milestones",
        json={"title": "First $500", "amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["reached_at"] is not None

    # List milestones
    r = client.get(f"/savings-goals/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 2

    # Delete milestone
    m_id = milestones[0]["id"]
    r = client.delete(
        f"/savings-goals/{goal_id}/milestones/{m_id}", headers=auth_header
    )
    assert r.status_code == 200

    # Confirm deleted
    r = client.get(f"/savings-goals/{goal_id}/milestones", headers=auth_header)
    assert len(r.get_json()) == 1


def test_milestone_auto_reach_on_update(client, auth_header):
    # Create goal with milestone
    r = client.post(
        "/savings-goals",
        json={"title": "Car Fund", "target_amount": 10000, "current_amount": 0},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings-goals/{goal_id}/milestones",
        json={"title": "Half way", "amount": 5000},
        headers=auth_header,
    )
    milestone_id = r.get_json()["id"]
    assert r.get_json()["reached_at"] is None

    # Update goal to pass milestone
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"current_amount": 6000},
        headers=auth_header,
    )
    assert r.status_code == 200

    # Check milestone is now reached
    r = client.get(f"/savings-goals/{goal_id}/milestones", headers=auth_header)
    milestones = r.get_json()
    reached = [m for m in milestones if m["id"] == milestone_id]
    assert len(reached) == 1
    assert reached[0]["reached_at"] is not None


def test_milestone_validation(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"title": "Test", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Missing title
    r = client.post(
        f"/savings-goals/{goal_id}/milestones",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid amount
    r = client.post(
        f"/savings-goals/{goal_id}/milestones",
        json={"title": "Bad", "amount": -10},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_milestone_not_found(client, auth_header):
    # Non-existent goal
    r = client.get("/savings-goals/9999/milestones", headers=auth_header)
    assert r.status_code == 404

    r = client.post(
        "/savings-goals/9999/milestones",
        json={"title": "X", "amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 404

    # Create a goal, then try non-existent milestone
    r = client.post(
        "/savings-goals",
        json={"title": "Test", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.delete(
        f"/savings-goals/{goal_id}/milestones/9999", headers=auth_header
    )
    assert r.status_code == 404


def test_savings_goal_defaults_to_user_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/savings-goals",
        json={"title": "Euro Goal", "target_amount": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"
