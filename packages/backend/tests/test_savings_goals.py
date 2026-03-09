from datetime import date, timedelta


def test_savings_goal_create_list_and_milestone_progress(client, auth_header):
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    payload = {
        "name": "Emergency Fund",
        "target_amount": 1000,
        "current_amount": 200,
        "target_date": (date.today() + timedelta(days=180)).isoformat(),
    }
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    goal = items[0]
    assert goal["id"] == goal_id
    assert goal["name"] == "Emergency Fund"
    assert goal["progress_pct"] == 20.0
    assert goal["remaining_amount"] == 800.0
    assert goal["status"] in ("on-track", "ahead", "behind")
    assert goal["next_milestone"]["percentage"] == 25

    r = client.post(
        f"/savings/goals/{goal_id}/contributions",
        json={"amount": 60},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["current_amount"] == 260.0
    assert updated["progress_pct"] == 26.0
    assert updated["newly_reached_milestones"] == [25]
    assert updated["next_milestone"]["percentage"] == 50


def test_savings_goal_validations_and_currency_default(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "INR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/savings/goals",
        json={"name": "Trip", "target_amount": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    created = next((goal for goal in r.get_json() if goal["id"] == goal_id), None)
    assert created is not None
    assert created["currency"] == "INR"

    r = client.post(
        f"/savings/goals/{goal_id}/contributions",
        json={"amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "amount" in r.get_json()["error"]

    r = client.post(
        "/savings/goals",
        json={"name": "Invalid Goal", "target_amount": -10},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "target_amount" in r.get_json()["error"]
