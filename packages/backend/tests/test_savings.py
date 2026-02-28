def test_create_goal(client, auth_header):
    r = client.post("/savings", json={
        "name": "Emergency Fund",
        "target_amount": 1000,
        "deadline": "2026-12-31",
    }, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 1000
    assert data["progress_pct"] == 0
    assert len(data["milestones"]) == 4


def test_create_goal_missing_fields(client, auth_header):
    r = client.post("/savings", json={"name": ""}, headers=auth_header)
    assert r.status_code == 400


def test_list_goals(client, auth_header):
    client.post("/savings", json={
        "name": "Vacation", "target_amount": 500,
    }, headers=auth_header)
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) >= 1


def test_get_goal_detail(client, auth_header):
    r = client.post("/savings", json={
        "name": "Car", "target_amount": 5000,
    }, headers=auth_header)
    gid = r.get_json()["id"]
    r = client.get(f"/savings/{gid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Car"


def test_contribute_and_milestones(client, auth_header):
    r = client.post("/savings", json={
        "name": "Laptop", "target_amount": 100,
    }, headers=auth_header)
    gid = r.get_json()["id"]

    # Contribute 50 -> 50%
    r = client.post(f"/savings/{gid}/contribute", json={"amount": 50}, headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["progress_pct"] == 50.0
    reached = [m for m in data["milestones"] if m["reached"]]
    assert len(reached) == 2  # 25% and 50%

    # Contribute 50 more -> 100%
    r = client.post(f"/savings/{gid}/contribute", json={"amount": 50}, headers=auth_header)
    data = r.get_json()
    assert data["achieved"] is True
    assert data["progress_pct"] == 100.0
    reached = [m for m in data["milestones"] if m["reached"]]
    assert len(reached) == 4


def test_contribute_invalid_amount(client, auth_header):
    r = client.post("/savings", json={
        "name": "Test", "target_amount": 100,
    }, headers=auth_header)
    gid = r.get_json()["id"]
    r = client.post(f"/savings/{gid}/contribute", json={"amount": -10}, headers=auth_header)
    assert r.status_code == 400


def test_update_goal(client, auth_header):
    r = client.post("/savings", json={
        "name": "Old Name", "target_amount": 100,
    }, headers=auth_header)
    gid = r.get_json()["id"]
    r = client.patch(f"/savings/{gid}", json={"name": "New Name"}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "New Name"


def test_delete_goal(client, auth_header):
    r = client.post("/savings", json={
        "name": "Delete Me", "target_amount": 50,
    }, headers=auth_header)
    gid = r.get_json()["id"]
    r = client.delete(f"/savings/{gid}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/savings/{gid}", headers=auth_header)
    assert r.status_code == 404


def test_goal_not_found(client, auth_header):
    r = client.get("/savings/99999", headers=auth_header)
    assert r.status_code == 404


def test_requires_auth(client):
    r = client.get("/savings")
    assert r.status_code == 401
