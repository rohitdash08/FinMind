from decimal import Decimal


def test_create_account(client, auth_header):
    r = client.post(
        "/accounts",
        json={
            "name": "Main Checking",
            "type": "CURRENT",
            "balance": 5000,
            "currency": "INR",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Main Checking"
    assert data["type"] == "CURRENT"
    assert data["balance"] == 5000.0
    assert data["currency"] == "INR"
    assert data["is_default"] is False
    assert "id" in data
    assert "created_at" in data


def test_create_account_with_default(client, auth_header):
    r = client.post(
        "/accounts",
        json={
            "name": "Savings",
            "type": "SAVINGS",
            "balance": 10000,
            "is_default": True,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["is_default"] is True


def test_create_account_missing_name(client, auth_header):
    r = client.post(
        "/accounts",
        json={"type": "CURRENT", "balance": 100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "name required"


def test_create_account_invalid_type(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Bad", "type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "invalid type" in r.get_json()["error"]


def test_create_account_invalid_balance(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Bad", "type": "CURRENT", "balance": "not_a_number"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid balance"


def test_list_accounts(client, auth_header):
    # Create two accounts
    client.post(
        "/accounts",
        json={"name": "Checking", "type": "CURRENT", "balance": 2000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Savings", "type": "SAVINGS", "balance": 8000},
        headers=auth_header,
    )

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 2
    names = {a["name"] for a in data}
    assert names == {"Checking", "Savings"}


def test_list_accounts_empty(client, auth_header):
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_accounts_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 0.0
    assert data["accounts"] == []
    assert data["asset_allocation"] == []


def test_accounts_overview_with_data(client, auth_header):
    # Create multiple accounts of different types
    client.post(
        "/accounts",
        json={"name": "Checking", "type": "CURRENT", "balance": 3000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Savings", "type": "SAVINGS", "balance": 7000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Credit Card", "type": "CREDIT", "balance": -500},
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 9500.0
    assert len(data["accounts"]) == 3

    # Check asset allocation
    alloc_by_type = {a["type"]: a for a in data["asset_allocation"]}
    assert "CURRENT" in alloc_by_type
    assert "SAVINGS" in alloc_by_type
    assert "CREDIT" in alloc_by_type

    # Verify percentages: 3000+7000-500=9500 total
    # CURRENT: 3000/9500 ~31.58%, SAVINGS: 7000/9500 ~73.68%, CREDIT: -500/9500 ~-5.26%
    assert abs(alloc_by_type["CURRENT"]["share_pct"] - round(3000 / 9500 * 100, 2)) < 0.01
    assert abs(alloc_by_type["SAVINGS"]["share_pct"] - round(7000 / 9500 * 100, 2)) < 0.01
    assert alloc_by_type["CURRENT"]["amount"] == 3000.0
    assert alloc_by_type["SAVINGS"]["amount"] == 7000.0
    assert alloc_by_type["CREDIT"]["amount"] == -500.0


def test_accounts_overview_single_account(client, auth_header):
    client.post(
        "/accounts",
        json={"name": "Only One", "type": "INVESTMENT", "balance": 5000},
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 5000.0
    assert len(data["accounts"]) == 1
    assert len(data["asset_allocation"]) == 1
    assert data["asset_allocation"][0]["type"] == "INVESTMENT"
    assert data["asset_allocation"][0]["share_pct"] == 100.0


def test_endpoints_require_auth(client):
    r = client.get("/accounts")
    assert r.status_code == 401

    r = client.post("/accounts", json={"name": "X", "type": "CURRENT"})
    assert r.status_code == 401

    r = client.get("/accounts/overview")
    assert r.status_code == 401


def test_create_account_default_currency_from_user(client, auth_header):
    # User preferred_currency is INR by default
    r = client.post(
        "/accounts",
        json={"name": "No Currency", "type": "SAVINGS", "balance": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "INR"


def test_create_account_custom_currency(client, auth_header):
    r = client.post(
        "/accounts",
        json={
            "name": "USD Account",
            "type": "CURRENT",
            "balance": 500,
            "currency": "USD",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "USD"
