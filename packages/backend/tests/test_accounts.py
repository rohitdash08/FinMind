"""Tests for multi-account financial overview (issue #132)."""


def test_create_account(client, auth_header):
    r = client.post(
        "/accounts/",
        json={"name": "Main Checking", "type": "checking", "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Main Checking"
    assert data["type"] == "checking"
    assert data["currency"] == "USD"
    assert "id" in data


def test_create_account_requires_name(client, auth_header):
    r = client.post("/accounts/", json={}, headers=auth_header)
    assert r.status_code == 400


def test_list_accounts(client, auth_header):
    client.post(
        "/accounts/", json={"name": "Savings"}, headers=auth_header
    )
    client.post(
        "/accounts/", json={"name": "Credit Card", "type": "credit"},
        headers=auth_header,
    )
    r = client.get("/accounts/", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 2
    names = [a["name"] for a in data]
    assert "Savings" in names
    assert "Credit Card" in names


def test_get_single_account(client, auth_header):
    r = client.post(
        "/accounts/", json={"name": "Test Acct"}, headers=auth_header
    )
    acct_id = r.get_json()["id"]
    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Test Acct"


def test_delete_account(client, auth_header):
    r = client.post(
        "/accounts/", json={"name": "To Delete"}, headers=auth_header
    )
    acct_id = r.get_json()["id"]
    r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 404


def test_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["account_count"] == 0
    assert data["total_balance"] == 0
    assert data["accounts"] == []


def test_overview_with_accounts(client, auth_header):
    # Create two accounts
    r1 = client.post(
        "/accounts/", json={"name": "Checking"}, headers=auth_header
    )
    r2 = client.post(
        "/accounts/", json={"name": "Savings"}, headers=auth_header
    )
    assert r1.status_code == 201
    assert r2.status_code == 201

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["account_count"] == 2
    names = [a["name"] for a in data["accounts"]]
    assert "Checking" in names
    assert "Savings" in names
