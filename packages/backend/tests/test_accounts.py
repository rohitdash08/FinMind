import pytest


def _create_account(client, auth_header, **kwargs):
    payload = {
        "name": "My Checking",
        "account_type": "checking",
        "balance": 1000.00,
        "currency": "USD",
        "institution": "First Bank",
    }
    payload.update(kwargs)
    return client.post("/accounts", json=payload, headers=auth_header)


def test_accounts_require_auth(client):
    assert client.get("/accounts").status_code == 401
    assert client.post("/accounts", json={}).status_code == 401
    assert client.get("/accounts/overview").status_code == 401
    assert client.put("/accounts/1", json={}).status_code == 401
    assert client.delete("/accounts/1").status_code == 401


def test_list_empty(client, auth_header):
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_account_success(client, auth_header):
    r = _create_account(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "My Checking"
    assert data["account_type"] == "checking"
    assert data["balance"] == 1000.0
    assert data["currency"] == "USD"
    assert data["institution"] == "First Bank"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_account_missing_name(client, auth_header):
    r = client.post(
        "/accounts",
        json={"account_type": "savings", "balance": 500},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_account_invalid_type(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "X", "account_type": "invalid_type"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]


def test_create_account_invalid_balance(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "X", "account_type": "savings", "balance": "not-a-number"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "balance" in r.get_json()["error"]


def test_create_account_all_types(client, auth_header):
    for atype in ("checking", "savings", "credit_card", "investment", "other"):
        r = _create_account(client, auth_header, name=atype, account_type=atype)
        assert r.status_code == 201, f"failed for type {atype}: {r.get_json()}"
        assert r.get_json()["account_type"] == atype


def test_list_accounts(client, auth_header):
    _create_account(client, auth_header, name="A", account_type="checking")
    _create_account(client, auth_header, name="B", account_type="savings")

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2
    names = {i["name"] for i in items}
    assert names == {"A", "B"}


def test_get_single_account(client, auth_header):
    r = _create_account(client, auth_header)
    account_id = r.get_json()["id"]

    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == account_id


def test_get_account_not_found(client, auth_header):
    r = client.get("/accounts/9999", headers=auth_header)
    assert r.status_code == 404


def test_update_account(client, auth_header):
    r = _create_account(client, auth_header)
    account_id = r.get_json()["id"]

    r = client.put(
        f"/accounts/{account_id}",
        json={"name": "Updated Name", "balance": 2500.50, "is_active": False},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Updated Name"
    assert updated["balance"] == 2500.50
    assert updated["is_active"] is False


def test_update_account_partial(client, auth_header):
    r = _create_account(client, auth_header, balance=100.0)
    account_id = r.get_json()["id"]

    r = client.put(
        f"/accounts/{account_id}",
        json={"balance": 999.99},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["balance"] == 999.99
    assert updated["name"] == "My Checking"  # unchanged


def test_update_account_not_found(client, auth_header):
    r = client.put("/accounts/9999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404


def test_update_account_invalid_type(client, auth_header):
    r = _create_account(client, auth_header)
    account_id = r.get_json()["id"]

    r = client.put(
        f"/accounts/{account_id}",
        json={"account_type": "bad_type"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_delete_account(client, auth_header):
    r = _create_account(client, auth_header)
    account_id = r.get_json()["id"]

    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 404


def test_delete_account_not_found(client, auth_header):
    r = client.delete("/accounts/9999", headers=auth_header)
    assert r.status_code == 404


def test_inactive_accounts_excluded_by_default(client, auth_header):
    _create_account(client, auth_header, name="Active", is_active=True)
    r = _create_account(client, auth_header, name="Inactive", is_active=False)
    account_id = r.get_json()["id"]
    # Mark it inactive via update
    client.put(
        f"/accounts/{account_id}",
        json={"is_active": False},
        headers=auth_header,
    )

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    names = [a["name"] for a in r.get_json()]
    assert "Active" in names
    assert "Inactive" not in names


def test_include_inactive_param(client, auth_header):
    _create_account(client, auth_header, name="Active", is_active=True)
    r = _create_account(client, auth_header, name="WillDeactivate", is_active=True)
    account_id = r.get_json()["id"]
    client.put(
        f"/accounts/{account_id}",
        json={"is_active": False},
        headers=auth_header,
    )

    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    assert r.status_code == 200
    names = [a["name"] for a in r.get_json()]
    assert "Active" in names
    assert "WillDeactivate" in names


def test_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_accounts"] == 0
    assert data["totals_by_currency"] == {}
    assert data["by_type"] == []
    assert data["accounts"] == []


def test_overview_aggregation(client, auth_header):
    _create_account(
        client, auth_header, name="Check1", account_type="checking",
        balance=1000.0, currency="USD"
    )
    _create_account(
        client, auth_header, name="Check2", account_type="checking",
        balance=500.0, currency="USD"
    )
    _create_account(
        client, auth_header, name="Savings1", account_type="savings",
        balance=2000.0, currency="USD"
    )
    _create_account(
        client, auth_header, name="Euro", account_type="savings",
        balance=800.0, currency="EUR"
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["total_accounts"] == 4
    assert data["totals_by_currency"]["USD"] == pytest.approx(3500.0)
    assert data["totals_by_currency"]["EUR"] == pytest.approx(800.0)

    by_type = {entry["account_type"]: entry for entry in data["by_type"]}
    assert by_type["checking"]["count"] == 2
    assert by_type["checking"]["balances"]["USD"] == pytest.approx(1500.0)
    assert by_type["savings"]["count"] == 2
    assert by_type["savings"]["balances"]["USD"] == pytest.approx(2000.0)
    assert by_type["savings"]["balances"]["EUR"] == pytest.approx(800.0)

    assert len(data["accounts"]) == 4


def test_overview_excludes_inactive(client, auth_header):
    _create_account(client, auth_header, name="Active", balance=1000.0, currency="USD")
    r = _create_account(client, auth_header, name="Inactive", balance=9999.0, currency="USD")
    account_id = r.get_json()["id"]
    client.put(f"/accounts/{account_id}", json={"is_active": False}, headers=auth_header)

    r = client.get("/accounts/overview", headers=auth_header)
    data = r.get_json()
    assert data["total_accounts"] == 1
    assert data["totals_by_currency"]["USD"] == pytest.approx(1000.0)


def test_accounts_isolated_between_users(client, app_fixture):
    # Create two users
    client.post("/auth/register", json={"email": "user1@test.com", "password": "pass1234"})
    client.post("/auth/register", json={"email": "user2@test.com", "password": "pass5678"})

    r1 = client.post("/auth/login", json={"email": "user1@test.com", "password": "pass1234"})
    h1 = {"Authorization": f"Bearer {r1.get_json()['access_token']}"}
    r2 = client.post("/auth/login", json={"email": "user2@test.com", "password": "pass5678"})
    h2 = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}

    _create_account(client, h1, name="User1 Account")
    _create_account(client, h2, name="User2 Account")

    r = client.get("/accounts", headers=h1)
    names = [a["name"] for a in r.get_json()]
    assert "User1 Account" in names
    assert "User2 Account" not in names

    r = client.get("/accounts", headers=h2)
    names = [a["name"] for a in r.get_json()]
    assert "User2 Account" in names
    assert "User1 Account" not in names


def test_cannot_access_other_users_account(client, app_fixture):
    client.post("/auth/register", json={"email": "owner@test.com", "password": "pass1234"})
    client.post("/auth/register", json={"email": "other@test.com", "password": "pass5678"})

    r = client.post("/auth/login", json={"email": "owner@test.com", "password": "pass1234"})
    h_owner = {"Authorization": f"Bearer {r.get_json()['access_token']}"}
    r = client.post("/auth/login", json={"email": "other@test.com", "password": "pass5678"})
    h_other = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = _create_account(client, h_owner)
    account_id = r.get_json()["id"]

    assert client.get(f"/accounts/{account_id}", headers=h_other).status_code == 404
    assert client.put(f"/accounts/{account_id}", json={"name": "X"}, headers=h_other).status_code == 404
    assert client.delete(f"/accounts/{account_id}", headers=h_other).status_code == 404


def test_account_default_balance_zero(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Empty", "account_type": "savings"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["balance"] == 0.0


def test_account_no_institution(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Solo", "account_type": "other"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["institution"] is None
