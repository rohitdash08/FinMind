def _create_goal(client, auth_header, name="Vacation", target=5000.0):
    payload = {
        "name": name,
        "target_amount": target,
        "currency": "USD",
        "deadline": "2026-12-31",
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def test_savings_goals_crud(client, auth_header):
    # List empty
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create
    goal = _create_goal(client, auth_header)
    goal_id = goal["id"]
    assert goal["name"] == "Vacation"
    assert goal["target_amount"] == 5000.0
    assert goal["current_amount"] == 0.0
    assert goal["status"] == "ACTIVE"
    assert goal["currency"] == "USD"
    assert goal["deadline"] == "2026-12-31"

    # List with one goal
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Get single goal
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == goal_id
    assert "milestones" in data
    assert data["milestones"] == []

    # Update
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"name": "Hawaii Vacation", "target_amount": 7500.0},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Hawaii Vacation"
    assert updated["target_amount"] == 7500.0

    # Update status
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"status": "ABANDONED"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "ABANDONED"

    # Delete
    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_goal_create_validation(client, auth_header):
    # Missing name
    r = client.post(
        "/savings-goals",
        json={"target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid target_amount
    r = client.post(
        "/savings-goals",
        json={"name": "X", "target_amount": -5},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid deadline
    r = client.post(
        "/savings-goals",
        json={"name": "X", "target_amount": 100, "deadline": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_contribute_and_auto_complete(client, auth_header):
    goal = _create_goal(client, auth_header, target=100.0)
    goal_id = goal["id"]

    # Partial contribution
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 40.0},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 40.0
    assert data["status"] == "ACTIVE"

    # Full contribution triggers COMPLETED
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 60.0},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 100.0
    assert data["status"] == "COMPLETED"

    # Invalid contribution
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": -10},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_milestones_crud(client, auth_header):
    goal = _create_goal(client, auth_header, target=1000.0)
    goal_id = goal["id"]

    # Create milestone
    r = client.post(
        f"/savings-goals/{goal_id}/milestones",
        json={"name": "Halfway", "target_amount": 500.0},
        headers=auth_header,
    )
    assert r.status_code == 201
    ms = r.get_json()
    ms_id = ms["id"]
    assert ms["name"] == "Halfway"
    assert ms["target_amount"] == 500.0
    assert ms["reached"] is False
    assert ms["reached_at"] is None

    # Update milestone
    r = client.patch(
        f"/savings-goals/{goal_id}/milestones/{ms_id}",
        json={"name": "50% Mark"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "50% Mark"

    # Contribute past milestone triggers reached
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 600.0},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    milestones = data["milestones"]
    assert len(milestones) == 1
    assert milestones[0]["reached"] is True
    assert milestones[0]["reached_at"] is not None

    # Manually set reached
    r = client.patch(
        f"/savings-goals/{goal_id}/milestones/{ms_id}",
        json={"reached": False},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["reached"] is False
    assert r.get_json()["reached_at"] is None

    # Delete milestone
    r = client.delete(
        f"/savings-goals/{goal_id}/milestones/{ms_id}",
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.get_json()["milestones"] == []


def test_milestone_create_reached_if_goal_already_funded(client, auth_header):
    goal = _create_goal(client, auth_header, target=1000.0)
    goal_id = goal["id"]

    # Contribute first
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 800.0},
        headers=auth_header,
    )
    assert r.status_code == 200

    # Add milestone below current amount -> auto reached
    r = client.post(
        f"/savings-goals/{goal_id}/milestones",
        json={"name": "Quick win", "target_amount": 500.0},
        headers=auth_header,
    )
    assert r.status_code == 201
    ms = r.get_json()
    assert ms["reached"] is True
    assert ms["reached_at"] is not None


def test_not_found_404(client, auth_header):
    # Goal not found
    r = client.get("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.patch("/savings-goals/99999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.post(
        "/savings-goals/99999/contribute",
        json={"amount": 10},
        headers=auth_header,
    )
    assert r.status_code == 404

    r = client.post(
        "/savings-goals/99999/milestones",
        json={"name": "X", "target_amount": 10},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_milestone_not_found_on_wrong_goal(client, auth_header):
    goal = _create_goal(client, auth_header)
    goal_id = goal["id"]
    goal2 = _create_goal(client, auth_header, name="Other")

    r = client.post(
        f"/savings-goals/{goal_id}/milestones",
        json={"name": "M1", "target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 201
    ms_id = r.get_json()["id"]

    # Try to access milestone via wrong goal
    r = client.patch(
        f"/savings-goals/{goal2['id']}/milestones/{ms_id}",
        json={"name": "X"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_default_currency_from_user(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/savings-goals",
        json={"name": "Car", "target_amount": 20000},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"
