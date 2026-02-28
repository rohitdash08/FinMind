def test_create_account(client, auth_header):
    r = client.post("/accounts", json={
        "name": "Main Checking", "account_type": "checking", "balance": 5000,
    }, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Main Checking"
    assert data["balance"] == 5000


def test_create_invalid_type(client, auth_header):
    r = client.post("/accounts", json={
        "name": "Bad", "account_type": "crypto",
    }, headers=auth_header)
    assert r.status_code == 400


def test_create_missing_fields(client, auth_header):
    r = client.post("/accounts", json={"name": "No Type"}, headers=auth_header)
    assert r.status_code == 400


def test_list_accounts(client, auth_header):
    client.post("/accounts", json={
        "name": "A1", "account_type": "checking",
    }, headers=auth_header)
    client.post("/accounts", json={
        "name": "A2", "account_type": "savings",
    }, headers=auth_header)
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) >= 2


def test_get_account_detail(client, auth_header):
    r = client.post("/accounts", json={
        "name": "Detail", "account_type": "cash", "balance": 100,
    }, headers=auth_header)
    aid = r.get_json()["id"]
    r = client.get(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Detail"


def test_update_account(client, auth_header):
    r = client.post("/accounts", json={
        "name": "Old", "account_type": "checking",
    }, headers=auth_header)
    aid = r.get_json()["id"]
    r = client.patch(f"/accounts/{aid}", json={
        "name": "Updated", "balance": 999,
    }, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Updated"
    assert r.get_json()["balance"] == 999


def test_delete_account(client, auth_header):
    r = client.post("/accounts", json={
        "name": "Delete Me", "account_type": "cash",
    }, headers=auth_header)
    aid = r.get_json()["id"]
    r = client.delete(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 404


def test_overview(client, auth_header):
    client.post("/accounts", json={
        "name": "Check", "account_type": "checking", "balance": 3000,
    }, headers=auth_header)
    client.post("/accounts", json={
        "name": "Save", "account_type": "savings", "balance": 2000,
    }, headers=auth_header)
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 5000
    assert data["account_count"] == 2
    assert "checking" in data["by_type"]
    assert "savings" in data["by_type"]


def test_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_requires_auth(client):
    r = client.get("/accounts")
    assert r.status_code == 401
