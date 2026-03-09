from datetime import date


def _register_and_auth(client, email: str) -> dict[str, str]:
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _get_me(client, auth_header: dict[str, str]) -> dict:
    r = client.get("/auth/me", headers=auth_header)
    assert r.status_code == 200
    return r.get_json()


def test_household_create_join_leave_and_remove_member(client):
    owner_auth = _register_and_auth(client, "owner@example.com")
    member_auth = _register_and_auth(client, "member@example.com")
    member_me = _get_me(client, member_auth)

    r = client.post("/households", json={"name": "Home Budget"}, headers=owner_auth)
    assert r.status_code == 201
    created = r.get_json()
    assert created["name"] == "Home Budget"
    assert isinstance(created["invite_code"], str) and len(created["invite_code"]) >= 6
    household_id = created["id"]

    r = client.post(
        "/households/join",
        json={"invite_code": created["invite_code"]},
        headers=member_auth,
    )
    assert r.status_code == 200
    assert r.get_json()["household_id"] == household_id

    r = client.get("/households/current", headers=member_auth)
    assert r.status_code == 200
    current_household = r.get_json()
    assert current_household["id"] == household_id
    assert len(current_household["members"]) == 2

    r = client.post("/households/leave", headers=member_auth)
    assert r.status_code == 200

    r = client.get("/households/current", headers=member_auth)
    assert r.status_code == 404

    r = client.post(
        "/households/join",
        json={"invite_code": created["invite_code"]},
        headers=member_auth,
    )
    assert r.status_code == 200

    r = client.delete(
        f"/households/members/{member_me['id']}",
        headers=owner_auth,
    )
    assert r.status_code == 200

    r = client.get("/households/current", headers=member_auth)
    assert r.status_code == 404


def test_household_shared_categories_expenses_and_bills(client):
    owner_auth = _register_and_auth(client, "budget-owner@example.com")
    member_auth = _register_and_auth(client, "budget-member@example.com")
    outsider_auth = _register_and_auth(client, "budget-outsider@example.com")

    r = client.post(
        "/households", json={"name": "Shared Household"}, headers=owner_auth
    )
    assert r.status_code == 201
    household = r.get_json()
    household_id = household["id"]

    r = client.post(
        "/households/join",
        json={"invite_code": household["invite_code"]},
        headers=member_auth,
    )
    assert r.status_code == 200

    r = client.post(
        "/categories",
        json={"name": "Shared Groceries", "household_id": household_id},
        headers=owner_auth,
    )
    assert r.status_code == 201
    category_id = r.get_json()["id"]

    r = client.get("/categories", headers=member_auth)
    assert r.status_code == 200
    names = {item["name"] for item in r.get_json()}
    assert "Shared Groceries" in names

    r = client.post(
        "/expenses",
        json={
            "amount": 120.0,
            "description": "Weekly groceries",
            "date": "2026-03-01",
            "category_id": category_id,
            "household_id": household_id,
        },
        headers=member_auth,
    )
    assert r.status_code == 201

    r = client.get("/expenses?search=Weekly%20groceries", headers=owner_auth)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 59.99,
            "next_due_date": date.today().isoformat(),
            "cadence": "MONTHLY",
            "household_id": household_id,
        },
        headers=member_auth,
    )
    assert r.status_code == 201

    r = client.get("/bills", headers=owner_auth)
    assert r.status_code == 200
    bill_names = {item["name"] for item in r.get_json()}
    assert "Internet" in bill_names

    r = client.post(
        "/expenses",
        json={
            "amount": 50.0,
            "description": "Unauthorized shared expense",
            "date": "2026-03-02",
            "household_id": household_id,
        },
        headers=outsider_auth,
    )
    assert r.status_code == 403
