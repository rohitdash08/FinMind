def test_accounts_crud(client, auth_header):
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    r = client.post(
        "/accounts",
        json={"name": "Main Checking", "account_type": "CHECKING", "balance": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct = r.get_json()
    acct_id = acct["id"]
    assert acct["name"] == "Main Checking"
    assert acct["account_type"] == "CHECKING"
    assert acct["balance"] == 5000.0
    assert acct["is_default"] is False

    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Main Checking"

    r = client.patch(
        f"/accounts/{acct_id}",
        json={"name": "Primary Checking", "balance": 6000, "is_default": True},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Primary Checking"
    assert updated["balance"] == 6000.0
    assert updated["is_default"] is True

    r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/accounts", headers=auth_header)
    assert r.get_json() == []


def test_accounts_requires_name_and_valid_type(client, auth_header):
    r = client.post("/accounts", json={"account_type": "CHECKING"}, headers=auth_header)
    assert r.status_code == 400

    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_accounts_overview(client, auth_header):
    client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "balance": 5000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 10000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Credit Card", "account_type": "CREDIT_CARD", "balance": 1500},
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 16500.0
    assert len(data["accounts"]) == 3
    assert data["balance_by_type"]["CHECKING"] == 5000.0
    assert data["balance_by_type"]["SAVINGS"] == 10000.0
    assert data["balance_by_type"]["CREDIT_CARD"] == 1500.0
    assert data["net_worth"] == 13500.0


def test_accounts_net_worth_calculation(client, auth_header):
    client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "balance": 3000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Credit Card", "account_type": "CREDIT_CARD", "balance": 1000},
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    data = r.get_json()
    assert data["total_balance"] == 4000.0
    assert data["net_worth"] == 2000.0


def test_accounts_default_flag_only_one(client, auth_header):
    r1 = client.post(
        "/accounts",
        json={"name": "First", "account_type": "CHECKING", "balance": 100, "is_default": True},
        headers=auth_header,
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/accounts",
        json={"name": "Second", "account_type": "SAVINGS", "balance": 200, "is_default": True},
        headers=auth_header,
    )
    assert r2.status_code == 201
    second_id = r2.get_json()["id"]

    r = client.get("/accounts", headers=auth_header)
    accounts = r.get_json()
    defaults = [a for a in accounts if a["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == second_id


def test_account_transactions(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "My Account", "account_type": "CHECKING", "balance": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_id = r.get_json()["id"]

    r = client.get(f"/accounts/{acct_id}/transactions", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_accounts_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 0.0
    assert data["accounts"] == []
    assert data["net_worth"] == 0.0
