from datetime import date


def _register_and_login(client, email, password="password123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def test_create_household(client, auth_header):
    r = client.post("/households", json={"name": "My Family"}, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "My Family"
    assert "id" in data


def test_create_household_no_name(client, auth_header):
    r = client.post("/households", json={"name": ""}, headers=auth_header)
    assert r.status_code == 400


def test_list_households(client, auth_header):
    client.post("/households", json={"name": "House A"}, headers=auth_header)
    r = client.get("/households", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 1
    assert data[0]["role"] == "owner"


def test_invite_and_join(client, auth_header):
    # User 1 creates household
    r = client.post("/households", json={"name": "Shared Home"}, headers=auth_header)
    hid = r.get_json()["id"]

    # Generate invite
    r = client.post(f"/households/{hid}/invite", headers=auth_header)
    assert r.status_code == 201
    code = r.get_json()["invite_code"]

    # User 2 joins
    header2 = _register_and_login(client, "user2@example.com")
    r = client.post("/households/join", json={"invite_code": code}, headers=header2)
    assert r.status_code == 200
    assert r.get_json()["role"] == "member"


def test_join_invalid_code(client, auth_header):
    r = client.post(
        "/households/join", json={"invite_code": "bogus"}, headers=auth_header
    )
    assert r.status_code == 400


def test_members_list(client, auth_header):
    r = client.post("/households", json={"name": "Team"}, headers=auth_header)
    hid = r.get_json()["id"]

    r = client.get(f"/households/{hid}/members", headers=auth_header)
    assert r.status_code == 200
    members = r.get_json()
    assert len(members) == 1
    assert members[0]["role"] == "owner"


def test_household_summary(client, auth_header):
    r = client.post("/households", json={"name": "Budget Fam"}, headers=auth_header)
    hid = r.get_json()["id"]

    # Add expense
    today = date.today()
    client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Groceries",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    ym = today.strftime("%Y-%m")
    r = client.get(f"/households/{hid}/summary?month={ym}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spending"] == 200
    assert data["member_count"] == 1


def test_non_member_blocked(client, auth_header):
    r = client.post("/households", json={"name": "Private"}, headers=auth_header)
    hid = r.get_json()["id"]

    header2 = _register_and_login(client, "outsider@example.com")
    r = client.get(f"/households/{hid}/members", headers=header2)
    assert r.status_code == 403


def test_requires_auth(client):
    r = client.post("/households", json={"name": "No Auth"})
    assert r.status_code == 401
