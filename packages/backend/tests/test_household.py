"""Tests for shared household budgeting support (#134)."""

from datetime import date


def _auth(client, email="house@test.com", password="secret123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    data = r.get_json()
    access = data["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    uid = me.get_json()["id"]
    return {"Authorization": f"Bearer {access}"}, uid


def _create_household(client, auth, name="Test Family"):
    r = client.post("/households", json={"name": name}, headers=auth)
    assert r.status_code == 201
    return r.get_json()["id"]


# -- Household CRUD ---------------------------------------------------------

def test_create_household(client):
    auth, uid = _auth(client)
    r = client.post("/households", json={"name": "My Family"}, headers=auth)
    assert r.status_code == 201
    assert r.get_json()["name"] == "My Family"


def test_create_household_missing_name(client):
    auth, _ = _auth(client)
    r = client.post("/households", json={}, headers=auth)
    assert r.status_code == 400


def test_list_households(client):
    auth, _ = _auth(client)
    _create_household(client, auth, "Family A")
    _create_household(client, auth, "Family B")
    r = client.get("/households", headers=auth)
    assert r.status_code == 200
    assert len(r.get_json()["households"]) >= 2


def test_get_household(client):
    auth, uid = _auth(client)
    hid = _create_household(client, auth)
    r = client.get(f"/households/{hid}", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == hid
    assert len(data["members"]) == 1
    assert data["members"][0]["role"] == "OWNER"


# -- Members ----------------------------------------------------------------

def test_add_member(client):
    auth1, uid1 = _auth(client, "owner@test.com")
    auth2, uid2 = _auth(client, "member@test.com")
    hid = _create_household(client, auth1)

    r = client.post(
        f"/households/{hid}/members",
        json={"user_id": uid2, "role": "MEMBER"},
        headers=auth1,
    )
    assert r.status_code == 201

    # Verify member can see household
    r = client.get(f"/households/{hid}", headers=auth2)
    assert r.status_code == 200
    assert len(r.get_json()["members"]) == 2


def test_add_duplicate_member(client):
    auth1, uid1 = _auth(client, "dup_owner@test.com")
    auth2, uid2 = _auth(client, "dup_member@test.com")
    hid = _create_household(client, auth1)

    client.post(
        f"/households/{hid}/members",
        json={"user_id": uid2},
        headers=auth1,
    )
    r = client.post(
        f"/households/{hid}/members",
        json={"user_id": uid2},
        headers=auth1,
    )
    assert r.status_code == 409


def test_remove_member(client):
    auth1, uid1 = _auth(client, "rm_owner@test.com")
    auth2, uid2 = _auth(client, "rm_member@test.com")
    hid = _create_household(client, auth1)

    client.post(
        f"/households/{hid}/members",
        json={"user_id": uid2},
        headers=auth1,
    )
    r = client.delete(f"/households/{hid}/members/{uid2}", headers=auth1)
    assert r.status_code == 200


def test_viewer_cannot_add_member(client):
    auth1, uid1 = _auth(client, "v_owner@test.com")
    auth2, uid2 = _auth(client, "v_viewer@test.com")
    auth3, uid3 = _auth(client, "v_other@test.com")
    hid = _create_household(client, auth1)

    client.post(
        f"/households/{hid}/members",
        json={"user_id": uid2, "role": "VIEWER"},
        headers=auth1,
    )
    r = client.post(
        f"/households/{hid}/members",
        json={"user_id": uid3},
        headers=auth2,
    )
    assert r.status_code == 403


# -- Budgets ----------------------------------------------------------------

def test_create_and_list_budgets(client):
    auth, _ = _auth(client, "budget@test.com")
    hid = _create_household(client, auth)

    r = client.post(
        f"/households/{hid}/budgets",
        json={
            "name": "Groceries",
            "amount_limit": 5000,
            "period_start": "2025-01-01",
            "period_end": "2025-01-31",
        },
        headers=auth,
    )
    assert r.status_code == 201

    r = client.get(f"/households/{hid}/budgets", headers=auth)
    assert r.status_code == 200
    budgets = r.get_json()["budgets"]
    assert len(budgets) == 1
    assert budgets[0]["amount_limit"] == 5000
    assert budgets[0]["spent"] == 0
    assert budgets[0]["remaining"] == 5000


# -- Shared expenses --------------------------------------------------------

def test_add_and_list_expenses(client):
    auth, _ = _auth(client, "exp@test.com")
    hid = _create_household(client, auth)

    r = client.post(
        f"/households/{hid}/expenses",
        json={"amount": 250, "notes": "Milk", "spent_at": "2025-01-15"},
        headers=auth,
    )
    assert r.status_code == 201

    r = client.get(f"/households/{hid}/expenses", headers=auth)
    assert r.status_code == 200
    expenses = r.get_json()["expenses"]
    assert len(expenses) == 1
    assert expenses[0]["amount"] == 250


def test_expense_updates_budget_spent(client):
    auth, _ = _auth(client, "bexp@test.com")
    hid = _create_household(client, auth)

    # Create budget
    r = client.post(
        f"/households/{hid}/budgets",
        json={
            "name": "Food",
            "amount_limit": 1000,
            "period_start": "2025-01-01",
            "period_end": "2025-01-31",
        },
        headers=auth,
    )
    bid = r.get_json()["id"]

    # Add expense linked to budget
    client.post(
        f"/households/{hid}/expenses",
        json={"amount": 300, "budget_id": bid, "spent_at": "2025-01-10"},
        headers=auth,
    )

    r = client.get(f"/households/{hid}/budgets", headers=auth)
    budgets = r.get_json()["budgets"]
    assert budgets[0]["spent"] == 300
    assert budgets[0]["remaining"] == 700


def test_non_member_cannot_access(client):
    auth1, _ = _auth(client, "priv_owner@test.com")
    auth2, _ = _auth(client, "priv_outsider@test.com")
    hid = _create_household(client, auth1)

    r = client.get(f"/households/{hid}", headers=auth2)
    assert r.status_code == 403

    r = client.get(f"/households/{hid}/budgets", headers=auth2)
    assert r.status_code == 403

    r = client.get(f"/households/{hid}/expenses", headers=auth2)
    assert r.status_code == 403
