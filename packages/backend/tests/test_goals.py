"""Tests for savings goals endpoints."""


def test_list_goals_empty(client, auth_header):
    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_goal(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "Vacation Fund", "target_amount": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Vacation Fund"
    assert data["target_amount"] == 5000
    assert data["current_amount"] == 0
    assert data["progress_pct"] == 0
    assert data["achieved"] is False
    assert "id" in data


def test_create_goal_validates_name(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "", "target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_goal_validates_amount(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "Test", "target_amount": -10},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_get_goal_detail(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "Car", "target_amount": 20000},
        headers=auth_header,
    )
    gid = r.get_json()["id"]

    r = client.get(f"/goals/{gid}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "Car"
    assert "contributions" in data
    assert isinstance(data["contributions"], list)


def test_get_goal_not_found(client, auth_header):
    r = client.get("/goals/9999", headers=auth_header)
    assert r.status_code == 404


def test_update_goal(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "House", "target_amount": 100000},
        headers=auth_header,
    )
    gid = r.get_json()["id"]

    r = client.patch(
        f"/goals/{gid}",
        json={"name": "Dream House", "target_amount": 150000},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Dream House"
    assert r.get_json()["target_amount"] == 150000


def test_delete_goal(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "Temp", "target_amount": 100},
        headers=auth_header,
    )
    gid = r.get_json()["id"]

    r = client.delete(f"/goals/{gid}", headers=auth_header)
    assert r.status_code == 200

    r = client.get(f"/goals/{gid}", headers=auth_header)
    assert r.status_code == 404


def test_contribute_to_goal(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "Laptop", "target_amount": 1000},
        headers=auth_header,
    )
    gid = r.get_json()["id"]

    r = client.post(
        f"/goals/{gid}/contribute",
        json={"amount": 250, "notes": "Monthly savings"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["current_amount"] == 250
    assert data["progress_pct"] == 25.0
    assert data["achieved"] is False
    assert data["contribution"]["amount"] == 250
    assert data["milestone_reached"] is False


def test_contribute_validates_amount(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "Test", "target_amount": 100},
        headers=auth_header,
    )
    gid = r.get_json()["id"]

    r = client.post(
        f"/goals/{gid}/contribute",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_goal_achieved_milestone(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "Phone", "target_amount": 500},
        headers=auth_header,
    )
    gid = r.get_json()["id"]

    # First contribution
    client.post(
        f"/goals/{gid}/contribute",
        json={"amount": 300},
        headers=auth_header,
    )

    # Second contribution reaches target
    r = client.post(
        f"/goals/{gid}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["achieved"] is True
    assert data["milestone_reached"] is True
    assert data["current_amount"] == 550
    assert data["progress_pct"] == 110.0


def test_list_goals_after_creation(client, auth_header):
    client.post(
        "/goals",
        json={"name": "Goal A", "target_amount": 100},
        headers=auth_header,
    )
    client.post(
        "/goals",
        json={"name": "Goal B", "target_amount": 200},
        headers=auth_header,
    )

    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 2
    names = [g["name"] for g in data]
    assert "Goal A" in names
    assert "Goal B" in names


def test_goals_require_auth(client):
    assert client.get("/goals").status_code == 401
    assert client.post("/goals", json={"name": "X", "target_amount": 1}).status_code == 401
