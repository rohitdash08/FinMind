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
    }
    r = client.post("/accounts", json=payload, headers=auth_header)
    assert r.status_code == 201
    account = r.get_json()
    account_id = account["id"]
    assert account["name"] == "Main Checking"
    assert account["account_type"] == "CHECKING"
    assert account["balance"] == 5000.00
    assert account["currency"] == "USD"

    # Create savings account
    payload2 = {
        "name": "Emergency Fund",
        "account_type": "SAVINGS",
        "balance": 10000.00,
        "currency": "USD",
    }
    r = client.post("/accounts", json=payload2, headers=auth_header)
    assert r.status_code == 201
    savings_id = r.get_json()["id"]

    # List has 2
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2

    # Get single
    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Main Checking"

    # Update
    r = client.put(
        f"/accounts/{account_id}",
        json={"name": "Primary Checking", "balance": 5500.00},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Primary Checking"
    assert updated["balance"] == 5500.00

    # Delete (soft)
    r = client.delete(f"/accounts/{savings_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # List now has 1
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1


def test_accounts_overview(client, auth_header):
    # Create multiple accounts of different types
    accounts = [
        {"name": "Checking", "account_type": "CHECKING", "balance": 3000.00, "currency": "USD"},
        {"name": "Savings", "account_type": "SAVINGS", "balance": 10000.00, "currency": "USD"},
        {"name": "Credit Card", "account_type": "CREDIT", "balance": -2000.00, "currency": "USD"},
        {"name": "Investment", "account_type": "INVESTMENT", "balance": 15000.00, "currency": "USD"},
    ]
    for acc in accounts:
        r = client.post("/accounts", json=acc, headers=auth_header)
        assert r.status_code == 201

    # Get overview
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["summary"]["total_accounts"] == 4
    assert data["summary"]["total_assets"] == 28000.00  # 3000 + 10000 + 15000
    assert data["summary"]["total_liabilities"] == 2000.00
    assert data["summary"]["net_worth"] == 26000.00
    assert len(data["accounts"]) == 4
    assert "by_type" in data["summary"]


def test_account_create_validation(client, auth_header):
    # Missing name
    r = client.post("/accounts", json={"balance": 100}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]

    # Invalid account_type
    r = client.post(
        "/accounts",
        json={"name": "Bad", "account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]


def test_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.put("/accounts/99999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_account_defaults_to_user_preferred_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    payload = {"name": "Euro Account", "account_type": "SAVINGS", "balance": 500}
    r = client.post("/accounts", json=payload, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"
