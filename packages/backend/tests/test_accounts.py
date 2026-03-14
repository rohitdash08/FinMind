def test_accounts_crud(client, auth_header):
    # Initially empty
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create account
    payload = {
        "name": "Main Checking",
        "account_type": "BANK",
        "institution": "Chase",
        "balance": 5000.00,
        "currency": "USD",
        "color": "#10B981",
    }
    r = client.post("/accounts", json=payload, headers=auth_header)
    assert r.status_code == 201
    account = r.get_json()
    account_id = account["id"]
    assert account["name"] == "Main Checking"
    assert account["account_type"] == "BANK"
    assert account["institution"] == "Chase"
    assert account["balance"] == 5000.00
    assert account["currency"] == "USD"
    assert account["color"] == "#10B981"
    assert account["active"] is True

    # List has 1
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == account_id

    # Get single
    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Main Checking"

    # Update
    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Primary Checking", "balance": 5500},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Primary Checking"
    assert r.get_json()["balance"] == 5500.0

    # Delete
    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # List empty again
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_account_validation(client, auth_header):
    # Missing required name
    r = client.post("/accounts", json={}, headers=auth_header)
    assert r.status_code == 400

    # Invalid account_type
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Not found
    r = client.get("/accounts/9999", headers=auth_header)
    assert r.status_code == 404


def test_accounts_overview(client, auth_header):
    # Create multiple accounts of different types
    accounts_data = [
        {"name": "Checking", "account_type": "BANK", "balance": 3000, "currency": "USD"},
        {"name": "Savings", "account_type": "BANK", "balance": 10000, "currency": "USD"},
        {"name": "Credit Card", "account_type": "CREDIT", "balance": 2000, "currency": "USD"},
        {"name": "401k", "account_type": "INVESTMENT", "balance": 50000, "currency": "USD"},
        {"name": "Wallet", "account_type": "CASH", "balance": 200, "currency": "USD"},
    ]
    for data in accounts_data:
        r = client.post("/accounts", json=data, headers=auth_header)
        assert r.status_code == 201

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    overview = r.get_json()

    assert overview["account_count"] == 5
    # total_balance = 3000 + 10000 + 2000 + 50000 + 200 = 65200
    assert overview["total_balance"] == 65200.0
    # assets = 3000 + 10000 + 50000 + 200 = 63200
    assert overview["total_assets"] == 63200.0
    # liabilities = abs(2000) = 2000
    assert overview["total_liabilities"] == 2000.0
    # net_worth = 63200 - 2000 = 61200
    assert overview["net_worth"] == 61200.0

    # Check type breakdown
    breakdown = {item["type"]: item for item in overview["type_breakdown"]}
    assert "BANK" in breakdown
    assert breakdown["BANK"]["count"] == 2
    assert breakdown["BANK"]["total"] == 13000.0
    assert "CREDIT" in breakdown
    assert breakdown["CREDIT"]["count"] == 1
    assert "INVESTMENT" in breakdown
    assert "CASH" in breakdown


def test_account_defaults_to_user_preferred_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/accounts",
        json={"name": "Euro Account"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_include_inactive_filter(client, auth_header):
    # Create and deactivate an account
    r = client.post(
        "/accounts",
        json={"name": "Old Account", "account_type": "BANK"},
        headers=auth_header,
    )
    account_id = r.get_json()["id"]
    client.patch(
        f"/accounts/{account_id}",
        json={"active": False},
        headers=auth_header,
    )

    # Default list excludes inactive
    r = client.get("/accounts", headers=auth_header)
    assert len(r.get_json()) == 0

    # With include_inactive
    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    assert len(r.get_json()) == 1


def test_update_invalid_account_type(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "BANK"},
        headers=auth_header,
    )
    account_id = r.get_json()["id"]
    r = client.patch(
        f"/accounts/{account_id}",
        json={"account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400
