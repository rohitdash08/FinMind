"""Tests for multi-account financial overview."""


def _auth_header(client):
    email = "accounts@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def test_create_account(client):
    headers = _auth_header(client)
    r = client.post(
        "/accounts/",
        json={"name": "Main Checking", "account_type": "checking", "balance": 5000},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.get_json()["account"]
    assert data["name"] == "Main Checking"
    assert data["balance"] == 5000


def test_list_accounts(client):
    headers = _auth_header(client)
    client.post("/accounts/", json={"name": "Savings", "account_type": "savings", "balance": 10000}, headers=headers)
    r = client.get("/accounts/", headers=headers)
    assert r.status_code == 200
    assert len(r.get_json()["accounts"]) >= 1


def test_overview_aggregation(client):
    headers = _auth_header(client)
    client.post("/accounts/", json={"name": "Checking", "account_type": "checking", "balance": 3000}, headers=headers)
    client.post("/accounts/", json={"name": "Credit Card", "account_type": "credit", "balance": -1000}, headers=headers)
    client.post("/accounts/", json={"name": "Investment", "account_type": "investment", "balance": 5000}, headers=headers)

    r = client.get("/accounts/overview", headers=headers)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_assets"] >= 8000
    assert data["total_liabilities"] >= 1000
    assert "net_worth" in data
    assert "by_type" in data


def test_update_balance(client):
    headers = _auth_header(client)
    r = client.post("/accounts/", json={"name": "Update Me", "account_type": "cash", "balance": 100}, headers=headers)
    aid = r.get_json()["account"]["id"]

    r = client.patch(f"/accounts/{aid}", json={"balance": 200}, headers=headers)
    assert r.status_code == 200
    assert r.get_json()["account"]["balance"] == 200


def test_delete_deactivates(client):
    headers = _auth_header(client)
    r = client.post("/accounts/", json={"name": "Delete Me", "account_type": "other", "balance": 0}, headers=headers)
    aid = r.get_json()["account"]["id"]

    r = client.delete(f"/accounts/{aid}", headers=headers)
    assert r.status_code == 200
