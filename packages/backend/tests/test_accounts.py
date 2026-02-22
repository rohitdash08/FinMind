"""Tests for multi-account financial overview."""


def test_create_account(client, auth_header):
    r = client.post("/accounts", json={
        "name": "Main Checking",
        "account_type": "CHECKING",
        "currency": "USD",
        "balance": 1500.00,
    }, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Main Checking"
    assert data["balance"] == 1500.00


def test_create_account_no_name(client, auth_header):
    r = client.post("/accounts", json={"name": ""}, headers=auth_header)
    assert r.status_code == 400


def test_list_accounts(client, auth_header):
    client.post("/accounts", json={"name": "Acc1", "balance": 100}, headers=auth_header)
    client.post("/accounts", json={"name": "Acc2", "balance": 200}, headers=auth_header)

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_update_account(client, auth_header):
    r = client.post("/accounts", json={"name": "Old", "balance": 100}, headers=auth_header)
    aid = r.get_json()["id"]

    r = client.patch(f"/accounts/{aid}", json={"name": "New", "balance": 500}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "New"
    assert r.get_json()["balance"] == 500.0


def test_delete_account(client, auth_header):
    r = client.post("/accounts", json={"name": "Gone"}, headers=auth_header)
    aid = r.get_json()["id"]

    r = client.delete(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/accounts", headers=auth_header)
    assert len(r.get_json()) == 0


def test_overview(client, auth_header):
    client.post("/accounts", json={
        "name": "Checking", "account_type": "CHECKING", "balance": 1000, "currency": "USD"
    }, headers=auth_header)
    client.post("/accounts", json={
        "name": "Savings", "account_type": "SAVINGS", "balance": 5000, "currency": "USD"
    }, headers=auth_header)
    client.post("/accounts", json={
        "name": "EUR Account", "account_type": "CHECKING", "balance": 2000, "currency": "EUR"
    }, headers=auth_header)

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_accounts"] == 3
    assert data["total_balance"] == 8000.0
    assert len(data["by_type"]) == 2  # CHECKING, SAVINGS
    assert len(data["by_currency"]) == 2  # USD, EUR


def test_overview_excludes_inactive(client, auth_header):
    r = client.post("/accounts", json={"name": "Active", "balance": 100}, headers=auth_header)
    client.post("/accounts", json={"name": "Inactive", "balance": 999}, headers=auth_header)
    aid2 = client.get("/accounts", headers=auth_header).get_json()[0]["id"]
    # Deactivate
    client.patch(f"/accounts/{aid2}", json={"is_active": False}, headers=auth_header)

    r = client.get("/accounts/overview", headers=auth_header)
    data = r.get_json()
    assert data["total_accounts"] == 1


def test_accounts_unauthorized(client):
    r = client.get("/accounts")
    assert r.status_code in (401, 422)
