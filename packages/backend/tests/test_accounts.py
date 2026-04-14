from datetime import date


def test_accounts_crud(client, auth_header):
    # Initially empty
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create checking account
    payload = {
        "name": "Main Checking",
        "account_type": "CHECKING",
        "balance": 5000.00,
        "currency": "USD",
        "institution": "Chase Bank",
    }
    r = client.post("/accounts", json=payload, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    account_id = data["id"]
    assert data["name"] == "Main Checking"
    assert data["account_type"] == "CHECKING"
    assert data["balance"] == 5000.00
    assert data["currency"] == "USD"
    assert data["institution"] == "Chase Bank"
    assert data["is_active"] is True

    # Create savings account
    r = client.post("/accounts", json={
        "name": "Emergency Fund",
        "account_type": "SAVINGS",
        "balance": 10000.00,
        "currency": "USD",
    }, headers=auth_header)
    assert r.status_code == 201
    savings_id = r.get_json()["id"]

    # Create credit card (negative balance)
    r = client.post("/accounts", json={
        "name": "Visa Card",
        "account_type": "CREDIT_CARD",
        "balance": -1500.00,
        "currency": "USD",
    }, headers=auth_header)
    assert r.status_code == 201

    # List should have 3
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 3

    # Get single account
    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Main Checking"

    # Update account
    r = client.put(f"/accounts/{account_id}", json={
        "name": "Primary Checking",
        "balance": 5500.00,
    }, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Primary Checking"
    assert r.get_json()["balance"] == 5500.00

    # Delete (soft delete)
    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 204

    # List should have 2 (active only)
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2

    # Include inactive shows 3
    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 3


def test_accounts_validation(client, auth_header):
    # Missing name
    r = client.post("/accounts", json={"balance": 100}, headers=auth_header)
    assert r.status_code == 400

    # Invalid account type
    r = client.post("/accounts", json={"name": "Test", "account_type": "INVALID"}, headers=auth_header)
    assert r.status_code == 400

    # Invalid balance
    r = client.post("/accounts", json={"name": "Test", "balance": "not_a_number"}, headers=auth_header)
    assert r.status_code == 400


def test_accounts_overview(client, auth_header):
    # Create multiple accounts
    client.post("/accounts", json={
        "name": "Checking",
        "account_type": "CHECKING",
        "balance": 3000.00,
        "currency": "USD",
    }, headers=auth_header)
    client.post("/accounts", json={
        "name": "Savings",
        "account_type": "SAVINGS",
        "balance": 8000.00,
        "currency": "USD",
    }, headers=auth_header)
    client.post("/accounts", json={
        "name": "Credit Card",
        "account_type": "CREDIT_CARD",
        "balance": -2000.00,
        "currency": "USD",
    }, headers=auth_header)

    # Get overview
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["account_count"] == 3
    assert data["total_assets"] == 11000.00
    assert data["total_liabilities"] == -2000.00
    assert data["net_worth"] == 9000.00
    assert len(data["accounts"]) == 3
    assert len(data["by_type"]) >= 2


def test_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.put("/accounts/99999", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404
