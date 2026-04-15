from datetime import date, timedelta


def test_savings_goals_crud(client, auth_header):
    # Create a goal
    payload = {
        "name": "Emergency Fund",
        "target_amount": 10000,
        "currency": "USD",
        "deadline": (date.today() + timedelta(days=180)).isoformat(),
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # List goals — has 1
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert any(g["id"] == goal_id for g in items)

    # Get single goal
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    g = r.get_json()
    assert g["name"] == "Emergency Fund"
    assert g["target_amount"] == 10000.0
    assert g["current_amount"] == 0.0
    assert g["status"] == "ACTIVE"
    assert g["milestones"] == []

    # Update goal name
    r = client.patch(f"/savings/{goal_id}", json={"name": "Revised Fund"}, headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.get_json()["name"] == "Revised Fund"

    # Contribute to goal
    r = client.post(f"/savings/{goal_id}/contribute", json={"amount": 2500}, headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 2500.0
    assert data["status"] == "ACTIVE"

    # Auto-complete when target reached
    r = client.post(f"/savings/{goal_id}/contribute", json={"amount": 7500}, headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 10000.0
    assert data["status"] == "COMPLETED"

    # Delete goal
    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_savings_milestones(client, auth_header):
    # Create goal
    payload = {"name": "Vacation", "target_amount": 5000, "currency": "USD"}
    r = client.post("/savings", json=payload, headers=auth_header)
    goal_id = r.get_json()["id"]

    # Add milestones
    ms1 = {"title": "Flights", "target_amount": 1500}
    r = client.post(f"/savings/{goal_id}/milestones", json=ms1, headers=auth_header)
    assert r.status_code == 201
    ms1_id = r.get_json()["id"]

    ms2 = {"title": "Hotel", "target_amount": 3500}
    r = client.post(f"/savings/{goal_id}/milestones", json=ms2, headers=auth_header)
    assert r.status_code == 201
    ms2_id = r.get_json()["id"]

    # List milestones
    r = client.get(f"/savings/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 2
    assert all(m["reached"] is False for m in milestones)

    # Contribute — reaches first milestone
    r = client.post(f"/savings/{goal_id}/contribute", json={"amount": 1500}, headers=auth_header)
    assert r.status_code == 200

    r = client.get(f"/savings/{goal_id}/milestones", headers=auth_header)
    milestones = r.get_json()
    reached = [m for m in milestones if m["reached"]]
    assert len(reached) == 1
    assert reached[0]["title"] == "Flights"

    # Update milestone
    r = client.patch(
        f"/savings/{goal_id}/milestones/{ms1_id}",
        json={"title": "Flights Booked"},
        headers=auth_header,
    )
    assert r.status_code == 200

    # Delete milestone
    r = client.delete(f"/savings/{goal_id}/milestones/{ms2_id}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/savings/{goal_id}/milestones", headers=auth_header)
    assert len(r.get_json()) == 1


def test_savings_goal_unauthorized(client):
    r = client.get("/savings")
    assert r.status_code == 401


def test_savings_contribute_negative_amount(client, auth_header):
    payload = {"name": "Test", "target_amount": 1000, "currency": "USD"}
    r = client.post("/savings", json=payload, headers=auth_header)
    goal_id = r.get_json()["id"]

    r = client.post(f"/savings/{goal_id}/contribute", json={"amount": -100}, headers=auth_header)
    assert r.status_code == 400
