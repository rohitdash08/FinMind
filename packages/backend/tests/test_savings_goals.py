from datetime import date


def test_savings_goals_list_empty(client, auth_header):
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_goals_create(client, auth_header):
    payload = {
        "name": "Emergency Fund",
        "target_amount": 10000,
        "currency": "USD",
        "deadline": "2026-12-31",
    }
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 10000.0
    assert data["current_amount"] == 0.0
    assert data["currency"] == "USD"
    assert data["deadline"] == "2026-12-31"
    assert data["progress"] == 0.0
    assert len(data["milestones"]) == 4
    assert [m["percent"] for m in data["milestones"]] == [25, 50, 75, 100]
    assert all(m["reached"] is False for m in data["milestones"])


def test_savings_goals_create_defaults_user_currency(client, auth_header):
    client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    payload = {"name": "Vacation", "target_amount": 5000}
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_savings_goals_create_validation(client, auth_header):
    r = client.post("/savings/goals", json={}, headers=auth_header)
    assert r.status_code == 400

    r = client.post(
        "/savings/goals",
        json={"name": "Bad", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_goals_get_by_id(client, auth_header):
    payload = {"name": "Car", "target_amount": 20000}
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Car"


def test_savings_goals_get_not_found(client, auth_header):
    r = client.get("/savings/goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_savings_goals_update(client, auth_header):
    payload = {"name": "House", "target_amount": 50000}
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    goal_id = r.get_json()["id"]

    r = client.patch(
        f"/savings/goals/{goal_id}",
        json={"name": "Dream House", "target_amount": 60000},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Dream House"
    assert r.get_json()["target_amount"] == 60000.0


def test_savings_goals_delete(client, auth_header):
    payload = {"name": "Temp Goal", "target_amount": 1000}
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    goal_id = r.get_json()["id"]

    r = client.delete(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # Should not appear in list
    r = client.get("/savings/goals", headers=auth_header)
    assert all(g["id"] != goal_id for g in r.get_json())


def test_savings_goals_contribute(client, auth_header):
    payload = {"name": "Fund", "target_amount": 1000}
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 250.0
    assert data["progress"] == 25.0
    # 25% milestone should be reached
    m25 = next(m for m in data["milestones"] if m["percent"] == 25)
    assert m25["reached"] is True


def test_savings_goals_contribute_validation(client, auth_header):
    payload = {"name": "Fund2", "target_amount": 1000}
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_goals_milestones_progression(client, auth_header):
    payload = {"name": "Milestone Test", "target_amount": 100}
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    goal_id = r.get_json()["id"]

    # Contribute 50 → 50% milestone
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 50},
        headers=auth_header,
    )
    data = r.get_json()
    assert data["progress"] == 50.0
    reached = [m["percent"] for m in data["milestones"] if m["reached"]]
    assert 25 in reached
    assert 50 in reached
    assert 75 not in reached

    # Contribute 50 more → 100%
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 50},
        headers=auth_header,
    )
    data = r.get_json()
    assert data["progress"] == 100.0
    assert all(m["reached"] for m in data["milestones"])


def test_savings_goals_list_after_create(client, auth_header):
    client.post(
        "/savings/goals",
        json={"name": "G1", "target_amount": 100},
        headers=auth_header,
    )
    client.post(
        "/savings/goals",
        json={"name": "G2", "target_amount": 200},
        headers=auth_header,
    )
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    goals = r.get_json()
    names = [g["name"] for g in goals]
    assert "G1" in names
    assert "G2" in names


def test_savings_goals_contribute_not_found(client, auth_header):
    r = client.post(
        "/savings/goals/99999/contribute",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 404
