def test_accounts_crud(client, auth_header):
    # List empty
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create
    payload = {
        "name": "Chase Checking",
        "account_type": "CHECKING",
        "institution": "Chase",
        "balance": 5000.50,
        "currency": "USD",
    }
    r = client.post("/accounts", json=payload, headers=auth_header)
    assert r.status_code == 201
    created = r.get_json()
    account_id = created["id"]
    assert created["name"] == "Chase Checking"
    assert created["account_type"] == "CHECKING"
    assert created["institution"] == "Chase"
    assert created["balance"] == 5000.50
    assert created["currency"] == "USD"
    assert created["is_active"] is True

    # Get single
    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Chase Checking"

    # Update
    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Chase Primary", "balance": 6000},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Chase Primary"
    assert updated["balance"] == 6000.0

    # List should have 1
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Delete
    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200

    # List should be empty again
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_account_create_validation(client, auth_header):
    # Missing name
    r = client.post("/accounts", json={"account_type": "CHECKING"}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]

    # Missing account_type
    r = client.post("/accounts", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]

    # Invalid account_type
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]

    # Invalid balance
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "CHECKING", "balance": "not_a_number"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "balance" in r.get_json()["error"]


def test_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.patch("/accounts/99999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_account_update_validation(client, auth_header):
    # Create an account first
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "SAVINGS", "balance": 100},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    # Empty name
    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "  "},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid type
    r = client.patch(
        f"/accounts/{account_id}",
        json={"account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid balance
    r = client.patch(
        f"/accounts/{account_id}",
        json={"balance": "abc"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_accounts_overview(client, auth_header):
    # Create multiple accounts
    accounts = [
        {"name": "Checking 1", "account_type": "CHECKING", "institution": "Chase", "balance": 5000, "currency": "USD"},
        {"name": "Savings 1", "account_type": "SAVINGS", "institution": "Chase", "balance": 10000, "currency": "USD"},
        {"name": "Credit Card", "account_type": "CREDIT_CARD", "institution": "Amex", "balance": -2000, "currency": "USD"},
        {"name": "INR Savings", "account_type": "SAVINGS", "institution": "SBI", "balance": 50000, "currency": "INR"},
    ]
    for a in accounts:
        r = client.post("/accounts", json=a, headers=auth_header)
        assert r.status_code == 201

    # Get overview
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    overview = r.get_json()

    assert overview["total_accounts"] == 4
    assert overview["total_balance"] == 63000.0  # 5000 + 10000 - 2000 + 50000

    # Check by_type
    type_map = {t["type"]: t for t in overview["by_type"]}
    assert "CHECKING" in type_map
    assert type_map["CHECKING"]["count"] == 1
    assert type_map["SAVINGS"]["count"] == 2
    assert type_map["SAVINGS"]["total_balance"] == 60000.0
    assert type_map["CREDIT_CARD"]["count"] == 1

    # Check by_currency
    currency_map = {c["currency"]: c["balance"] for c in overview["by_currency"]}
    assert currency_map["USD"] == 13000.0  # 5000 + 10000 - 2000
    assert currency_map["INR"] == 50000.0

    # Check by_institution
    inst_map = {i["institution"]: i for i in overview["by_institution"]}
    assert inst_map["Chase"]["count"] == 2
    assert inst_map["Amex"]["count"] == 1
    assert inst_map["SBI"]["count"] == 1


def test_accounts_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    overview = r.get_json()
    assert overview["total_accounts"] == 0
    assert overview["total_balance"] == 0
    assert overview["by_type"] == []
    assert overview["by_currency"] == []
    assert overview["by_institution"] == []


def test_account_defaults_to_user_currency(client, auth_header):
    # Set user preferred currency
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/accounts",
        json={"name": "Euro Account", "account_type": "CHECKING"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_account_types(client, auth_header):
    valid_types = ["CHECKING", "SAVINGS", "CREDIT_CARD", "INVESTMENT", "LOAN", "OTHER"]
    for account_type in valid_types:
        r = client.post(
            "/accounts",
            json={"name": f"Test {account_type}", "account_type": account_type},
            headers=auth_header,
        )
        assert r.status_code == 201, f"Failed for type {account_type}"
        assert r.get_json()["account_type"] == account_type


def test_inactive_accounts_filtered(client, auth_header):
    # Create and deactivate
    r = client.post(
        "/accounts",
        json={"name": "Old Account", "account_type": "CHECKING", "balance": 100},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    r = client.patch(
        f"/accounts/{account_id}",
        json={"is_active": False},
        headers=auth_header,
    )
    assert r.status_code == 200

    # Default list excludes inactive
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 0

    # include_inactive shows it
    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1
