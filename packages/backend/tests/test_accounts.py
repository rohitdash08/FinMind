"""Tests for multi-account financial overview."""


def _create_account(client, auth_header, name="Checking", account_type="checking", balance=1000):
    r = client.post("/accounts", json={"name": name, "account_type": account_type, "balance": balance}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


# 1. Auth required
def test_accounts_requires_auth(client):
    r = client.get("/accounts")
    assert r.status_code in (401, 422)


# 2. Create account
def test_create_account(client, auth_header):
    data = _create_account(client, auth_header, "My Checking", "checking", 5000)
    assert data["name"] == "My Checking"
    assert data["account_type"] == "checking"
    assert data["balance"] == 5000.0
    assert data["active"] is True


# 3. List accounts
def test_list_accounts(client, auth_header):
    _create_account(client, auth_header, "Account A", "checking", 1000)
    _create_account(client, auth_header, "Account B", "savings", 5000)
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) >= 2


# 4. Update balance
def test_update_balance(client, auth_header):
    acc = _create_account(client, auth_header, "Savings", "savings", 2000)
    r = client.patch(f"/accounts/{acc['id']}", json={"balance": 3500}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["balance"] == 3500.0


# 5. Delete account
def test_delete_account(client, auth_header):
    acc = _create_account(client, auth_header, "ToDelete", "cash", 100)
    r = client.delete(f"/accounts/{acc['id']}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/accounts/{acc['id']}", headers=auth_header)
    assert r.status_code == 404


# 6. Invalid account type
def test_invalid_account_type(client, auth_header):
    r = client.post("/accounts", json={"name": "Bad", "account_type": "invalid_type"}, headers=auth_header)
    assert r.status_code == 400


# 7. Missing name
def test_missing_name(client, auth_header):
    r = client.post("/accounts", json={"name": "", "account_type": "checking"}, headers=auth_header)
    assert r.status_code == 400


# 8. Overview aggregation
def test_overview(client, auth_header):
    _create_account(client, auth_header, "Checking", "checking", 10000)
    _create_account(client, auth_header, "Savings", "savings", 25000)
    _create_account(client, auth_header, "Credit Card", "credit", -3000)
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_accounts"] == 3
    assert data["total_balance"] == 32000.0
    assert data["assets"] == 35000.0
    assert data["liabilities"] == 3000.0
    assert data["net_worth"] == 32000.0
    assert "checking" in data["by_type"]
    assert "savings" in data["by_type"]


# 9. Get single account
def test_get_single(client, auth_header):
    acc = _create_account(client, auth_header, "Investment", "investment", 50000)
    r = client.get(f"/accounts/{acc['id']}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Investment"


# 10. Overview with no accounts
def test_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_accounts"] == 0
    assert data["total_balance"] == 0
    assert data["net_worth"] == 0
