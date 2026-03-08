from datetime import date, timedelta


def test_savings_goals_crud(client, auth_header):
    # Initially empty
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create savings goal
    payload = {
        "name": "Emergency Fund",
        "target_amount": 10000,
        "currency": "USD",
        "deadline": (date.today() + timedelta(days=180)).isoformat(),
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 10000
    assert goal["current_amount"] == 0
    assert goal["progress_percent"] == 0
    assert goal["completed"] is False

    # Get single goal
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == goal_id

    # Contribute to goal
    r = client.post(f"/savings/{goal_id}/contribute", json={"amount": 2500}, headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["current_amount"] == 2500
    assert goal["progress_percent"] == 25.0

    # Update goal
    r = client.patch(f"/savings/{goal_id}", json={"current_amount": 5000}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 5000

    # Delete goal
    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200

    # Verify deleted
    r = client.get("/savings", headers=auth_header)
    assert r.get_json() == []


def test_savings_goal_with_milestones(client, auth_header):
    # Create goal with milestones
    payload = {
        "name": "Vacation Fund",
        "target_amount": 5000,
        "currency": "USD",
        "milestones": [
            {"title": "Flight tickets", "target_amount": 1500},
            {"title": "Hotel", "target_amount": 3500},
        ],
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Check milestones created
    r = client.get(f"/savings/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 2
    assert milestones[0]["title"] == "Flight tickets"
    assert milestones[0]["reached"] is False

    # Contribute to reach first milestone
    r = client.post(f"/savings/{goal_id}/contribute", json={"amount": 1600}, headers=auth_header)
    assert r.status_code == 200

    # Check milestone reached
    r = client.get(f"/savings/{goal_id}/milestones", headers=auth_header)
    milestones = r.get_json()
    assert milestones[0]["reached"] is True
    assert milestones[1]["reached"] is False

    # Add milestone later
    r = client.post(f"/savings/{goal_id}/milestones", json={
        "title": "Activities",
        "target_amount": 4500
    }, headers=auth_header)
    assert r.status_code == 201

    # Delete milestone
    r = client.delete(f"/savings/{goal_id}/milestones/1", headers=auth_header)
    assert r.status_code == 200


def test_savings_goal_completion(client, auth_header):
    # Create goal
    payload = {
        "name": "New Laptop",
        "target_amount": 2000,
        "currency": "USD",
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Contribute enough to complete
    r = client.post(f"/savings/{goal_id}/contribute", json={"amount": 2000}, headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["completed"] is True
    assert goal["progress_percent"] == 100.0


def test_savings_goal_defaults_to_user_currency(client, auth_header):
    # Set preferred currency
    r = client.patch("/auth/me", json={"preferred_currency": "INR"}, headers=auth_header)
    assert r.status_code == 200

    # Create goal without specifying currency
    payload = {
        "name": "Test Goal",
        "target_amount": 5000,
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["currency"] == "INR"
