"""Tests for shared household budgeting (issue #134)."""


def _register_and_login(client, email, password="secret123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def test_create_household(client, auth_header):
    r = client.post(
        "/household/", json={"name": "Smith Family"}, headers=auth_header
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Smith Family"
    assert len(data["members"]) == 1
    assert data["members"][0]["role"] == "owner"


def test_create_requires_name(client, auth_header):
    r = client.post("/household/", json={}, headers=auth_header)
    assert r.status_code == 400


def test_get_household(client, auth_header):
    client.post("/household/", json={"name": "Test House"}, headers=auth_header)
    r = client.get("/household/", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Test House"


def test_invite_member(client, auth_header):
    client.post("/household/", json={"name": "Duo"}, headers=auth_header)

    # Register second user
    partner_header = _register_and_login(client, "partner@test.com")

    r = client.post(
        "/household/invite",
        json={"email": "partner@test.com"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["members"]) == 2


def test_invite_duplicate(client, auth_header):
    client.post("/household/", json={"name": "Dup"}, headers=auth_header)
    _register_and_login(client, "dup@test.com")
    client.post(
        "/household/invite", json={"email": "dup@test.com"}, headers=auth_header
    )
    r = client.post(
        "/household/invite", json={"email": "dup@test.com"}, headers=auth_header
    )
    assert r.status_code == 409


def test_remove_member(client, auth_header):
    client.post("/household/", json={"name": "Trio"}, headers=auth_header)
    _register_and_login(client, "removable@test.com")
    client.post(
        "/household/invite",
        json={"email": "removable@test.com"},
        headers=auth_header,
    )

    # Get the member's user_id
    r = client.get("/household/", headers=auth_header)
    members = r.get_json()["members"]
    removable = [m for m in members if m["email"] == "removable@test.com"][0]

    r = client.delete(
        f"/household/members/{removable['user_id']}", headers=auth_header
    )
    assert r.status_code == 200


def test_household_summary(client, auth_header):
    from datetime import date

    client.post("/household/", json={"name": "Budget House"}, headers=auth_header)

    # Add an expense
    client.post(
        "/expenses",
        json={
            "amount": 150,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    ym = date.today().strftime("%Y-%m")
    r = client.get(f"/household/summary?month={ym}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_expenses"] >= 150
    assert data["member_count"] >= 1
    assert len(data["per_member"]) >= 1


def test_no_household_returns_404(client):
    header = _register_and_login(client, "lonely@test.com")
    r = client.get("/household/", headers=header)
    assert r.status_code == 404
