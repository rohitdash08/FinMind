from datetime import date, timedelta


def test_savings_goal_crud(client, auth_header):
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    r = client.post(
        "/savings/goals",
        json={"name": "Emergency Fund", "target_amount": 10000, "target_date": "2027-01-01"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 10000.0
    assert goal["current_amount"] == 0.0
    assert goal["progress_pct"] == 0.0

    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Emergency Fund"

    r = client.patch(
        f"/savings/goals/{goal_id}",
        json={"name": "Emergency Fund Updated", "target_amount": 15000},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Emergency Fund Updated"
    assert r.get_json()["target_amount"] == 15000.0

    r = client.delete(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/savings/goals", headers=auth_header)
    assert r.get_json() == []


def test_savings_goal_requires_name_and_positive_amount(client, auth_header):
    r = client.post("/savings/goals", json={"target_amount": 1000}, headers=auth_header)
    assert r.status_code == 400

    r = client.post("/savings/goals", json={"name": "Test", "target_amount": -100}, headers=auth_header)
    assert r.status_code == 400

    r = client.post("/savings/goals", json={"name": "Test", "target_amount": 0}, headers=auth_header)
    assert r.status_code == 400


def test_savings_goal_contributions(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Vacation", "target_amount": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{goal_id}/contributions",
        json={"amount": 1500},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["current_amount"] == 1500.0
    assert goal["progress_pct"] == 30.0

    r = client.post(
        f"/savings/goals/{goal_id}/contributions",
        json={"amount": 3500},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["current_amount"] == 5000.0
    assert goal["progress_pct"] == 100.0

    r = client.get(f"/savings/goals/{goal_id}/contributions", headers=auth_header)
    assert r.status_code == 200
    contributions = r.get_json()
    assert len(contributions) == 2
    assert contributions[0]["amount"] == 3500.0

    r = client.post(
        f"/savings/goals/{goal_id}/contributions",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_goal_milestones(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Car Down Payment", "target_amount": 10000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings/goals/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 4
    assert milestones[0] == {"percentage": 25, "amount": 2500.0, "reached": False}
    assert milestones[3] == {"percentage": 100, "amount": 10000.0, "reached": False}

    client.post(
        f"/savings/goals/{goal_id}/contributions",
        json={"amount": 5000},
        headers=auth_header,
    )

    r = client.get(f"/savings/goals/{goal_id}/milestones", headers=auth_header)
    milestones = r.get_json()
    assert milestones[0]["reached"] is True
    assert milestones[1]["reached"] is True
    assert milestones[2]["reached"] is False
    assert milestones[3]["reached"] is False


def test_savings_goal_days_left(client, auth_header):
    future_date = (date.today() + timedelta(days=90)).isoformat()
    r = client.post(
        "/savings/goals",
        json={"name": "Short-term", "target_amount": 1000, "target_date": future_date},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["days_left"] is not None
    assert goal["days_left"] > 0


def test_savings_goal_invalid_target_date(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Bad date", "target_amount": 1000, "target_date": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_goal_not_found(client, auth_header):
    r = client.get("/savings/goals/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.post("/savings/goals/99999/contributions", json={"amount": 100}, headers=auth_header)
    assert r.status_code == 404
