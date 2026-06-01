from datetime import date, timedelta


def test_savings_goals_empty_initially(client, auth_header):
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_savings_goal(client, auth_header):
    payload = {
        "title": "Emergency Fund",
        "target_amount": 10000,
        "current_amount": 2500,
        "currency": "USD",
        "deadline": (date.today() + timedelta(days=180)).isoformat(),
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["title"] == "Emergency Fund"
    assert data["target"] == 10000.0
    assert data["current"] == 2500.0
    assert data["currency"] == "USD"
    assert data["status"] in ("on-track", "ahead", "behind", "completed")
    assert isinstance(data["monthlyTarget"], (int, float))
    return data["id"]


def test_list_savings_goals_after_create(client, auth_header):
    client.post(
        "/savings",
        json={"title": "Vacation Fund", "target_amount": 3000},
        headers=auth_header,
    )
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) >= 1
    assert any(g["title"] == "Vacation Fund" for g in items)


def test_get_savings_goal(client, auth_header):
    r = client.post(
        "/savings",
        json={"title": "Car Fund", "target_amount": 20000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == goal_id


def test_get_savings_goal_not_found(client, auth_header):
    r = client.get("/savings/9999", headers=auth_header)
    assert r.status_code == 404


def test_update_savings_goal(client, auth_header):
    r = client.post(
        "/savings",
        json={"title": "House Down Payment", "target_amount": 50000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.patch(
        f"/savings/{goal_id}",
        json={"title": "House Deposit", "target_amount": 60000},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["title"] == "House Deposit"
    assert data["target"] == 60000.0


def test_update_savings_goal_not_found(client, auth_header):
    r = client.patch(
        "/savings/9999",
        json={"title": "X"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_contribute_to_savings_goal(client, auth_header):
    r = client.post(
        "/savings",
        json={"title": "Laptop Fund", "target_amount": 1500, "current_amount": 0},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current"] == 500.0

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current"] == 1500.0
    assert data["status"] == "completed"


def test_contribute_invalid_amount(client, auth_header):
    r = client.post(
        "/savings",
        json={"title": "Misc Fund", "target_amount": 500},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_delete_savings_goal(client, auth_header):
    r = client.post(
        "/savings",
        json={"title": "Temp Goal", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_create_goal_missing_title(client, auth_header):
    r = client.post(
        "/savings",
        json={"target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_goal_invalid_target(client, auth_header):
    r = client.post(
        "/savings",
        json={"title": "Bad Goal", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_goal_invalid_deadline(client, auth_header):
    r = client.post(
        "/savings",
        json={"title": "Bad Deadline Goal", "target_amount": 1000, "deadline": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_goal_status_behind(client, auth_header):
    past_deadline = (date.today() - timedelta(days=30)).isoformat()
    r = client.post(
        "/savings",
        json={"title": "Overdue Goal", "target_amount": 1000, "deadline": past_deadline},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["status"] == "behind"


def test_goal_status_completed(client, auth_header):
    r = client.post(
        "/savings",
        json={"title": "Completed Goal", "target_amount": 500, "current_amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["status"] == "completed"


def test_goal_defaults_to_user_currency(client, auth_header):
    client.patch("/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header)
    r = client.post(
        "/savings",
        json={"title": "Euro Goal", "target_amount": 2000},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["currency"] == "EUR"


def test_goals_isolated_per_user(client):
    # Register two different users
    for email in ["user1@example.com", "user2@example.com"]:
        client.post("/auth/register", json={"email": email, "password": "pw123456"})

    def login(email):
        r = client.post("/auth/login", json={"email": email, "password": "pw123456"})
        token = r.get_json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    h1 = login("user1@example.com")
    h2 = login("user2@example.com")

    client.post("/savings", json={"title": "User1 Goal", "target_amount": 1000}, headers=h1)

    r = client.get("/savings", headers=h2)
    assert r.status_code == 200
    items = r.get_json()
    assert not any(g["title"] == "User1 Goal" for g in items)
