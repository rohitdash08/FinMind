"""Tests for the multi-account financial overview feature."""

from datetime import date


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_account(client, auth_header):
    r = client.post(
        "/accounts",
        json={
            "name": "Main Checking",
            "account_type": "CHECKING",
            "institution": "HDFC Bank",
            "balance": 25000.50,
            "currency": "INR",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Main Checking"
    assert data["account_type"] == "CHECKING"
    assert data["institution"] == "HDFC Bank"
    assert data["balance"] == 25000.50
    assert data["is_active"] is True


def test_create_account_name_required(client, auth_header):
    r = client.post(
        "/accounts",
        json={"account_type": "SAVINGS"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_account_invalid_type(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Bad", "account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]


def test_list_accounts(client, auth_header):
    # Create two accounts
    client.post(
        "/accounts",
        json={"name": "Checking", "balance": 1000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 5000},
        headers=auth_header,
    )
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    accounts = r.get_json()
    assert len(accounts) == 2


def test_get_account(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Test", "balance": 100},
        headers=auth_header,
    )
    aid = r.get_json()["id"]
    r = client.get(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Test"


def test_update_account(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Old Name", "balance": 100},
        headers=auth_header,
    )
    aid = r.get_json()["id"]
    r = client.patch(
        f"/accounts/{aid}",
        json={"name": "New Name", "balance": 200},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "New Name"
    assert r.get_json()["balance"] == 200.0


def test_delete_account_soft_deletes(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "To Deactivate", "balance": 100},
        headers=auth_header,
    )
    aid = r.get_json()["id"]
    r = client.delete(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200

    # Should not appear in default listing
    r = client.get("/accounts", headers=auth_header)
    assert all(a["id"] != aid for a in r.get_json())

    # Should appear when include_inactive
    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    accts = r.get_json()
    deactivated = [a for a in accts if a["id"] == aid]
    assert len(deactivated) == 1
    assert deactivated[0]["is_active"] is False


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def test_accounts_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["net_worth"] == 0
    assert data["total_assets"] == 0
    assert data["total_liabilities"] == 0
    assert data["account_count"] == 0
    assert isinstance(data["accounts"], list)


def test_accounts_overview_with_data(client, auth_header):
    # Create accounts: checking (asset), savings (asset), credit card (liability)
    client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "balance": 10000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 50000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Visa Card", "account_type": "CREDIT_CARD", "balance": 5000},
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["total_assets"] == 60000.0
    assert data["total_liabilities"] == 5000.0
    assert data["net_worth"] == 55000.0
    assert data["account_count"] == 3
    assert len(data["accounts"]) == 3


def test_accounts_overview_with_transactions(client, auth_header):
    # Create account
    r = client.post(
        "/accounts",
        json={"name": "Primary", "balance": 10000},
        headers=auth_header,
    )
    account_id = r.get_json()["id"]

    # Create income transaction linked to account
    r = client.post(
        "/expenses",
        json={
            "amount": 5000,
            "description": "Salary",
            "date": date.today().isoformat(),
            "expense_type": "INCOME",
            "account_id": account_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Create expense transaction linked to account
    r = client.post(
        "/expenses",
        json={
            "amount": 1500,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
            "account_id": account_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    # Check aggregate
    assert data["aggregate"]["monthly_income"] >= 5000
    assert data["aggregate"]["monthly_expenses"] >= 1500

    # Check per-account breakdown
    primary = [a for a in data["accounts"] if a["name"] == "Primary"][0]
    assert primary["monthly_income"] == 5000.0
    assert primary["monthly_expenses"] == 1500.0
    assert primary["monthly_net"] == 3500.0
    assert primary["transaction_count"] == 2

    # Recent transactions included
    assert len(data["recent_transactions"]) >= 2


def test_accounts_overview_month_filter(client, auth_header):
    r = client.get("/accounts/overview?month=2025-01", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["period"]["month"] == "2025-01"


def test_accounts_overview_invalid_month(client, auth_header):
    r = client.get("/accounts/overview?month=invalid", headers=auth_header)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Per-account transactions
# ---------------------------------------------------------------------------


def test_account_transactions(client, auth_header):
    # Create account and linked transaction
    r = client.post(
        "/accounts",
        json={"name": "Transaction Test", "balance": 1000},
        headers=auth_header,
    )
    account_id = r.get_json()["id"]

    client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Coffee",
            "date": date.today().isoformat(),
            "account_id": account_id,
        },
        headers=auth_header,
    )

    r = client.get(f"/accounts/{account_id}/transactions", headers=auth_header)
    assert r.status_code == 200
    txns = r.get_json()
    assert len(txns) == 1
    assert txns[0]["description"] == "Coffee"
    assert txns[0]["account_id"] == account_id


def test_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_nonexistent_account(client, auth_header):
    r = client.patch(
        "/accounts/99999",
        json={"name": "X"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_delete_nonexistent_account(client, auth_header):
    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_all_account_types(client, auth_header):
    types = ["CHECKING", "SAVINGS", "CREDIT_CARD", "INVESTMENT", "LOAN", "CASH", "OTHER"]
    for t in types:
        r = client.post(
            "/accounts",
            json={"name": f"{t} Account", "account_type": t, "balance": 1000},
            headers=auth_header,
        )
        assert r.status_code == 201, f"Failed for type {t}"
        assert r.get_json()["account_type"] == t


def test_account_transactions_not_found(client, auth_header):
    r = client.get("/accounts/99999/transactions", headers=auth_header)
    assert r.status_code == 404
