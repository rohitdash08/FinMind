from datetime import date


def test_multi_account_overview_tracks_balances_and_unassigned_activity(client, auth_header):
    checking = client.post(
        "/accounts",
        json={
            "name": "Primary Checking",
            "account_type": "CHECKING",
            "currency": "USD",
            "opening_balance": 1000,
            "institution": "Test Bank",
        },
        headers=auth_header,
    )
    assert checking.status_code == 201
    checking_id = checking.get_json()["id"]

    credit = client.post(
        "/accounts",
        json={"name": "Rewards Card", "account_type": "CREDIT", "opening_balance": 200},
        headers=auth_header,
    )
    assert credit.status_code == 201
    credit_id = credit.get_json()["id"]

    salary = client.post(
        "/expenses",
        json={
            "amount": 2500,
            "description": "Paycheck",
            "date": date.today().isoformat(),
            "expense_type": "INCOME",
            "account_id": checking_id,
        },
        headers=auth_header,
    )
    assert salary.status_code == 201
    assert salary.get_json()["account_id"] == checking_id

    groceries = client.post(
        "/expenses",
        json={
            "amount": 125,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
            "account_id": checking_id,
        },
        headers=auth_header,
    )
    assert groceries.status_code == 201

    card_charge = client.post(
        "/expenses",
        json={
            "amount": 75,
            "description": "Card dinner",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
            "account_id": credit_id,
        },
        headers=auth_header,
    )
    assert card_charge.status_code == 201

    unassigned = client.post(
        "/expenses",
        json={
            "amount": 20,
            "description": "Cash snack",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert unassigned.status_code == 201

    month = date.today().strftime("%Y-%m")
    response = client.get(f"/accounts/overview?month={month}", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()

    assert data["summary"]["account_count"] == 2
    assert data["summary"]["monthly_income"] == 2500.0
    assert data["summary"]["monthly_expenses"] == 220.0
    assert data["unassigned_activity"]["expenses"] == 20.0

    by_name = {account["name"]: account for account in data["accounts"]}
    assert by_name["Primary Checking"]["computed_balance"] == 3375.0
    assert by_name["Primary Checking"]["net_flow"] == 2375.0
    assert by_name["Rewards Card"]["computed_balance"] == 125.0
    assert data["summary"]["total_assets"] == 3375.0
    assert data["summary"]["total_liabilities"] == 125.0
    assert data["summary"]["net_worth"] == 3250.0


def test_accounts_crud_and_invalid_month_validation(client, auth_header):
    created = client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "opening_balance": "50.55"},
        headers=auth_header,
    )
    assert created.status_code == 201
    account_id = created.get_json()["id"]

    listed = client.get("/accounts", headers=auth_header)
    assert listed.status_code == 200
    assert any(account["id"] == account_id for account in listed.get_json())

    patched = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Emergency Savings", "opening_balance": 75, "active": True},
        headers=auth_header,
    )
    assert patched.status_code == 200
    assert patched.get_json()["name"] == "Emergency Savings"
    assert patched.get_json()["opening_balance"] == 75.0

    invalid = client.get("/accounts/overview?month=2026-99", headers=auth_header)
    assert invalid.status_code == 400

    deleted = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert deleted.status_code == 200
    active_only = client.get("/accounts", headers=auth_header).get_json()
    assert all(account["id"] != account_id for account in active_only)
