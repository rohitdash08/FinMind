"""Tests for household budgeting feature."""


def _register_and_login(client, email, password="password123"):
    """Register a user and return auth header."""
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_household(client, auth_header):
    r = client.post("/household", json={"name": "Smith Family"}, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Smith Family"
    assert len(data["members"]) == 1
    assert data["members"][0]["role"] == "OWNER"


def test_create_household_no_name(client, auth_header):
    r = client.post("/household", json={"name": ""}, headers=auth_header)
    assert r.status_code == 400


def test_list_households(client, auth_header):
    client.post("/household", json={"name": "House A"}, headers=auth_header)
    client.post("/household", json={"name": "House B"}, headers=auth_header)

    r = client.get("/household", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_get_household(client, auth_header):
    r = client.post("/household", json={"name": "Test"}, headers=auth_header)
    hid = r.get_json()["id"]

    r = client.get(f"/household/{hid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Test"


def test_delete_household(client, auth_header):
    r = client.post("/household", json={"name": "ToDelete"}, headers=auth_header)
    hid = r.get_json()["id"]

    r = client.delete(f"/household/{hid}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/household", headers=auth_header)
    assert len(r.get_json()) == 0


def test_invite_and_join(client, auth_header):
    # User 1 creates household
    r = client.post("/household", json={"name": "Family"}, headers=auth_header)
    hid = r.get_json()["id"]

    # User 1 invites user 2
    email2 = "user2@example.com"
    r = client.post(
        f"/household/{hid}/invite",
        json={"email": email2},
        headers=auth_header,
    )
    assert r.status_code == 201
    token = r.get_json()["token"]

    # User 2 registers and joins
    auth2 = _register_and_login(client, email2)
    r = client.post("/household/join", json={"token": token}, headers=auth2)
    assert r.status_code == 200
    members = r.get_json()["members"]
    assert len(members) == 2


def test_join_invalid_token(client, auth_header):
    r = client.post(
        "/household/join",
        json={"token": "invalid-token"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_household_expenses(client, auth_header):
    # Create household
    r = client.post("/household", json={"name": "Shared"}, headers=auth_header)
    hid = r.get_json()["id"]

    # Add an expense (need a category first)
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    r = client.get("/categories", headers=auth_header)
    cat_id = r.get_json()[0]["id"]

    client.post(
        "/expenses",
        json={
            "amount": 42.00,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Groceries",
            "date": "2026-02-20",
        },
        headers=auth_header,
    )

    # View household expenses
    r = client.get(f"/household/{hid}/expenses", headers=auth_header)
    assert r.status_code == 200
    expenses = r.get_json()
    assert len(expenses) == 1
    assert expenses[0]["amount"] == 42.00


def test_household_expenses_not_member(client):
    auth1 = _register_and_login(client, "owner@test.com")
    auth2 = _register_and_login(client, "stranger@test.com")

    r = client.post("/household", json={"name": "Private"}, headers=auth1)
    hid = r.get_json()["id"]

    r = client.get(f"/household/{hid}/expenses", headers=auth2)
    assert r.status_code == 403


def test_household_unauthorized(client):
    r = client.get("/household")
    assert r.status_code in (401, 422)
