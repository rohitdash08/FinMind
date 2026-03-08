from datetime import date


def test_create_and_list_goal(client, auth_header):
    r = client.post(
        "/goals",
        json={
            "title": "Emergency Fund",
            "target_amount": 1000,
            "current_amount": 250,
            "currency": "USD",
            "target_date": date.today().isoformat(),
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    payload = r.get_json()
    assert payload["title"] == "Emergency Fund"
    assert payload["progress_pct"] == 25.0

    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 1
    assert any(x["title"] == "Emergency Fund" for x in data)


def test_update_goal_progress(client, auth_header):
    r = client.post(
        "/goals",
        json={"title": "Vacation", "target_amount": 2000, "current_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 201
    gid = r.get_json()["id"]

    r = client.patch(
        f"/goals/{gid}",
        json={"current_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 200
    p = r.get_json()
    assert p["current_amount"] == 1000.0
    assert p["progress_pct"] == 50.0
    reached = [m for m in p["milestones"] if m["reached"]]
    assert any(m["percent"] == 25 for m in reached)
    assert any(m["percent"] == 50 for m in reached)
