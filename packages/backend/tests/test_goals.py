"""Tests for savings goals feature."""


def test_create_goal(client, auth_header):
    r = client.post("/goals", json={
        "name": "Emergency Fund",
        "target_amount": 10000,
        "currency": "USD",
        "deadline": "2026-12-31",
    }, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 10000
    assert data["progress_percent"] == 0
    assert data["completed"] is False


def test_create_goal_validation(client, auth_header):
    r = client.post("/goals", json={"name": "", "target_amount": 100}, headers=auth_header)
    assert r.status_code == 400

    r = client.post("/goals", json={"name": "X", "target_amount": -5}, headers=auth_header)
    assert r.status_code == 400


def test_list_goals(client, auth_header):
    client.post("/goals", json={"name": "A", "target_amount": 100}, headers=auth_header)
    client.post("/goals", json={"name": "B", "target_amount": 200}, headers=auth_header)

    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_update_goal(client, auth_header):
    r = client.post("/goals", json={"name": "Old", "target_amount": 500}, headers=auth_header)
    gid = r.get_json()["id"]

    r = client.patch(f"/goals/{gid}", json={"name": "New", "target_amount": 1000}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "New"
    assert r.get_json()["target_amount"] == 1000


def test_contribute(client, auth_header):
    r = client.post("/goals", json={"name": "Trip", "target_amount": 500}, headers=auth_header)
    gid = r.get_json()["id"]

    r = client.post(f"/goals/{gid}/contribute", json={"amount": 200}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 200
    assert r.get_json()["progress_percent"] == 40.0

    r = client.post(f"/goals/{gid}/contribute", json={"amount": 300}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 500
    assert r.get_json()["completed"] is True
    assert r.get_json()["progress_percent"] == 100.0


def test_contribute_validation(client, auth_header):
    r = client.post("/goals", json={"name": "X", "target_amount": 100}, headers=auth_header)
    gid = r.get_json()["id"]

    r = client.post(f"/goals/{gid}/contribute", json={"amount": -10}, headers=auth_header)
    assert r.status_code == 400


def test_auto_complete_on_update(client, auth_header):
    r = client.post("/goals", json={"name": "Car", "target_amount": 1000}, headers=auth_header)
    gid = r.get_json()["id"]

    r = client.patch(f"/goals/{gid}", json={"current_amount": 1500}, headers=auth_header)
    assert r.get_json()["completed"] is True


def test_delete_goal(client, auth_header):
    r = client.post("/goals", json={"name": "Gone", "target_amount": 50}, headers=auth_header)
    gid = r.get_json()["id"]

    r = client.delete(f"/goals/{gid}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/goals", headers=auth_header)
    assert len(r.get_json()) == 0


def test_goals_unauthorized(client):
    r = client.get("/goals")
    assert r.status_code in (401, 422)
