def test_savings_goal_lifecycle(client, auth_header):
    create = client.post(
        "/savings-goals",
        headers=auth_header,
        json={
            "name": "Emergency fund",
            "target_amount": "1000.00",
            "current_amount": "125.50",
            "currency": "USD",
            "target_date": "2026-12-31",
        },
    )
    assert create.status_code == 201
    goal = create.get_json()
    assert goal["name"] == "Emergency fund"
    assert goal["target_amount"] == 1000.0
    assert goal["current_amount"] == 125.5
    assert goal["remaining_amount"] == 874.5
    assert goal["progress_pct"] == 12.55
    goal_id = goal["id"]

    contribution = client.post(
        f"/savings-goals/{goal_id}/contributions",
        headers=auth_header,
        json={"amount": "374.50"},
    )
    assert contribution.status_code == 200
    updated = contribution.get_json()
    assert updated["current_amount"] == 500.0
    assert updated["remaining_amount"] == 500.0
    assert updated["progress_pct"] == 50.0

    patch = client.patch(
        f"/savings-goals/{goal_id}",
        headers=auth_header,
        json={"target_amount": "1200", "name": "Emergency reserve"},
    )
    assert patch.status_code == 200
    assert patch.get_json()["name"] == "Emergency reserve"
    assert patch.get_json()["target_amount"] == 1200.0

    listed = client.get("/savings-goals", headers=auth_header)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.get_json()] == [goal_id]

    archived = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert archived.status_code == 200

    active_only = client.get("/savings-goals", headers=auth_header)
    assert active_only.status_code == 200
    assert active_only.get_json() == []

    with_inactive = client.get(
        "/savings-goals?include_inactive=true", headers=auth_header
    )
    assert with_inactive.status_code == 200
    assert with_inactive.get_json()[0]["active"] is False


def test_savings_goal_validation(client, auth_header):
    missing_name = client.post(
        "/savings-goals", headers=auth_header, json={"target_amount": "100"}
    )
    assert missing_name.status_code == 400

    invalid_target = client.post(
        "/savings-goals",
        headers=auth_header,
        json={"name": "Trip", "target_amount": "0"},
    )
    assert invalid_target.status_code == 400

    invalid_date = client.post(
        "/savings-goals",
        headers=auth_header,
        json={"name": "Trip", "target_amount": "100", "target_date": "bad-date"},
    )
    assert invalid_date.status_code == 400

    goal = client.post(
        "/savings-goals",
        headers=auth_header,
        json={"name": "Trip", "target_amount": "100"},
    )
    assert goal.status_code == 201

    invalid_contribution = client.post(
        f"/savings-goals/{goal.get_json()['id']}/contributions",
        headers=auth_header,
        json={"amount": "-1"},
    )
    assert invalid_contribution.status_code == 400
