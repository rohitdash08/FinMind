def test_create_and_list_savings_goal_with_milestones(client, auth_header):
    res = client.post(
        "/savings-goals",
        headers=auth_header,
        json={
            "name": "Emergency fund",
            "target_amount": 1000,
            "current_amount": 250,
            "currency": "USD",
            "target_date": "2026-12-31",
            "milestones": [
                {"name": "First quarter", "amount": 250},
                {"name": "Halfway", "amount": 500},
            ],
        },
    )

    assert res.status_code == 201
    goal = res.get_json()
    assert goal["progress_pct"] == 25.0
    assert goal["remaining_amount"] == 750.0
    assert goal["milestones"][0]["reached"] is True
    assert goal["milestones"][1]["reached"] is False

    res = client.get("/savings-goals", headers=auth_header)
    assert res.status_code == 200
    assert res.get_json()[0]["name"] == "Emergency fund"


def test_update_goal_reaches_milestones_and_completes(client, auth_header):
    created = client.post(
        "/savings-goals",
        headers=auth_header,
        json={
            "name": "Laptop",
            "target_amount": 600,
            "current_amount": 100,
            "milestones": [{"name": "Ready to buy", "amount": 600}],
        },
    ).get_json()

    res = client.patch(
        f"/savings-goals/{created['id']}",
        headers=auth_header,
        json={"current_amount": 600},
    )

    assert res.status_code == 200
    goal = res.get_json()
    assert goal["status"] == "COMPLETED"
    assert goal["progress_pct"] == 100.0
    assert goal["milestones"][0]["reached"] is True
