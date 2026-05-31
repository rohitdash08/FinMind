from datetime import date


def test_goals_crud(client, auth_header):
    # Initially empty
    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        "title": "Emergency Fund",
        "description": "Save for emergencies",
        "target_amount": 50000,
        "currency": "INR",
        "deadline": "2026-12-31",
    }
    r = client.post("/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # List has 1
    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == goal_id
    assert items[0]["title"] == "Emergency Fund"
    assert items[0]["target_amount"] == 50000
    assert items[0]["current_amount"] == 0

    # Update goal
    r = client.patch(f"/goals/{goal_id}", json={"title": "Big Emergency Fund"}, headers=auth_header)
    assert r.status_code == 200
    r = client.get("/goals", headers=auth_header)
    assert r.get_json()[0]["title"] == "Big Emergency Fund"

    # Delete goal (soft delete)
    r = client.delete(f"/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    r = client.get("/goals", headers=auth_header)
    assert r.get_json() == []


def test_goal_contribute(client, auth_header):
    payload = {
        "title": "Vacation",
        "target_amount": 10000,
    }
    r = client.post("/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Contribute
    r = client.post(f"/goals/{goal_id}/contribute", json={"amount": 2500}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 2500

    # Contribute again
    r = client.post(f"/goals/{goal_id}/contribute", json={"amount": 1500}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 4000


def test_goal_milestones(client, auth_header):
    payload = {"title": "Car", "target_amount": 300000}
    r = client.post("/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Initially no milestones
    r = client.get(f"/goals/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create milestone
    r = client.post(
        f"/goals/{goal_id}/milestones",
        json={"label": "First 50k", "target_amount": 50000},
        headers=auth_header,
    )
    assert r.status_code == 201
    mid = r.get_json()["id"]

    # List milestones
    r = client.get(f"/goals/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    ms = r.get_json()
    assert len(ms) == 1
    assert ms[0]["label"] == "First 50k"

    # Delete milestone
    r = client.delete(f"/goals/{goal_id}/milestones/{mid}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/goals/{goal_id}/milestones", headers=auth_header)
    assert r.get_json() == []


def test_goal_not_found(client, auth_header):
    r = client.patch("/goals/9999", json={"title": "x"}, headers=auth_header)
    assert r.status_code == 404
    r = client.delete("/goals/9999", headers=auth_header)
    assert r.status_code == 404
    r = client.post("/goals/9999/contribute", json={"amount": 100}, headers=auth_header)
    assert r.status_code == 404


def test_goal_create_defaults_to_user_currency(client, auth_header):
    r = client.patch("/auth/me", json={"preferred_currency": "USD"}, headers=auth_header)
    assert r.status_code == 200

    payload = {"title": "Laptop", "target_amount": 2000}
    r = client.post("/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get("/goals", headers=auth_header)
    assert r.get_json()[0]["currency"] == "USD"
