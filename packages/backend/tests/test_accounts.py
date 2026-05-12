def test_accounts_crud_and_soft_delete(client, auth_header):
    r = client.post(
        "/accounts",
        json={
            "name": "Main Checking",
            "account_type": "checking",
            "balance": 1500,
            "currency": "USD",
            "institution": "Acme Bank",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    account = r.get_json()
    account_id = account["id"]
    assert account["account_type"] == "CHECKING"
    assert account["balance"] == 1500.0

    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Primary Checking", "balance": 1750.25},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Primary Checking"
    assert r.get_json()["balance"] == 1750.25

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_accounts_are_isolated_per_user(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Private Account", "account_type": "SAVINGS", "balance": 50},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    client.post(
        "/auth/register",
        json={"email": "other@example.com", "password": "password123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": "other@example.com", "password": "password123"},
    )
    other_header = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Stolen"},
        headers=other_header,
    )
    assert r.status_code == 404

    r = client.get("/accounts", headers=other_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_accounts_overview_aggregates_balances_and_activity(client, auth_header):
    checking = _create_account(client, auth_header, "Checking", "CHECKING", 2000)
    credit = _create_account(client, auth_header, "Credit Card", "CREDIT_CARD", 300)
    savings = _create_account(client, auth_header, "Savings", "SAVINGS", 5000)

    rows = [
        (checking, 3000, "Salary", "INCOME", "2026-05-03"),
        (checking, 120, "Groceries", "EXPENSE", "2026-05-04"),
        (credit, 80, "Dinner", "EXPENSE", "2026-05-05"),
        (savings, 400, "Transfer", "INCOME", "2026-04-30"),
    ]
    for account_id, amount, description, expense_type, spent_at in rows:
        r = client.post(
            "/expenses",
            json={
                "account_id": account_id,
                "amount": amount,
                "currency": "USD",
                "description": description,
                "expense_type": expense_type,
                "date": spent_at,
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        assert r.get_json()["account_id"] == account_id

    r = client.get("/accounts/overview?month=2026-05", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"] == {
        "account_count": 3,
        "assets": 7000.0,
        "liabilities": 300.0,
        "net_worth": 6700.0,
    }
    checking_row = next(row for row in payload["accounts"] if row["id"] == checking)
    assert checking_row["monthly_income"] == 3000.0
    assert checking_row["monthly_expenses"] == 120.0
    assert checking_row["monthly_net_flow"] == 2880.0
    assert checking_row["transaction_count"] == 2

    assert payload["by_currency"][0]["currency"] == "USD"
    assert payload["by_currency"][0]["net_worth"] == 6700.0
    assert any(row["account_type"] == "CREDIT_CARD" for row in payload["by_type"])
    assert payload["recent_transactions"][0]["account_name"] == "Credit Card"


def test_expense_account_filter_rejects_cross_user_account(client, auth_header):
    account_id = _create_account(client, auth_header, "Checking", "CHECKING", 100)

    client.post(
        "/auth/register",
        json={"email": "other2@example.com", "password": "password123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": "other2@example.com", "password": "password123"},
    )
    other_header = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = client.post(
        "/expenses",
        json={
            "account_id": account_id,
            "amount": 12,
            "description": "Should not link",
            "date": "2026-05-01",
        },
        headers=other_header,
    )
    assert r.status_code == 201
    assert r.get_json()["account_id"] is None


def _create_account(client, auth_header, name, account_type, balance):
    r = client.post(
        "/accounts",
        json={
            "name": name,
            "account_type": account_type,
            "balance": balance,
            "currency": "USD",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()["id"]
