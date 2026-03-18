"""Tests for /accounts CRUD and /dashboard/overview multi-account aggregation."""
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_account(client, headers, **kwargs):
    payload = {
        "name": kwargs.get("name", "Main Checking"),
        "account_type": kwargs.get("account_type", "CHECKING"),
        "balance": kwargs.get("balance", 1000),
        "institution": kwargs.get("institution", "Test Bank"),
        "currency": kwargs.get("currency", "INR"),
    }
    return client.post("/accounts", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------

def test_create_account_returns_201(client, auth_header):
    r = _create_account(client, auth_header, name="Salary Account", account_type="SAVINGS", balance=5000)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Salary Account"
    assert data["account_type"] == "SAVINGS"
    assert data["balance"] == 5000.0
    assert data["institution"] == "Test Bank"
    assert data["currency"] == "INR"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_account_invalid_type_returns_400(client, auth_header):
    r = _create_account(client, auth_header, account_type="BOGUS")
    assert r.status_code == 400
    assert "account_type" in r.get_json().get("error", "")


def test_create_account_missing_name_returns_400(client, auth_header):
    r = client.post("/accounts", json={"account_type": "CHECKING", "balance": 100}, headers=auth_header)
    assert r.status_code == 400


def test_create_account_invalid_balance_returns_400(client, auth_header):
    r = client.post("/accounts", json={"name": "X", "balance": "not-a-number"}, headers=auth_header)
    assert r.status_code == 400


def test_list_accounts_empty(client, auth_header):
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_accounts_returns_active_only_by_default(client, auth_header):
    _create_account(client, auth_header, name="Active Account")
    r1 = _create_account(client, auth_header, name="To Be Deactivated")
    acct_id = r1.get_json()["id"]
    # deactivate via PATCH
    client.patch(f"/accounts/{acct_id}", json={"is_active": False}, headers=auth_header)

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    names = [a["name"] for a in r.get_json()]
    assert "Active Account" in names
    assert "To Be Deactivated" not in names


def test_list_accounts_include_inactive(client, auth_header):
    _create_account(client, auth_header, name="Active")
    r1 = _create_account(client, auth_header, name="Inactive")
    client.patch(f"/accounts/{r1.get_json()['id']}", json={"is_active": False}, headers=auth_header)

    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    assert r.status_code == 200
    names = [a["name"] for a in r.get_json()]
    assert "Active" in names
    assert "Inactive" in names


def test_get_account_by_id(client, auth_header):
    r = _create_account(client, auth_header, name="Investment Portfolio", account_type="INVESTMENT", balance=25000)
    acct_id = r.get_json()["id"]

    r2 = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r2.status_code == 200
    data = r2.get_json()
    assert data["id"] == acct_id
    assert data["name"] == "Investment Portfolio"
    assert data["account_type"] == "INVESTMENT"


def test_get_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_account_name_and_balance(client, auth_header):
    r = _create_account(client, auth_header, name="Old Name", balance=100)
    acct_id = r.get_json()["id"]

    r2 = client.patch(f"/accounts/{acct_id}", json={"name": "New Name", "balance": 2500.50}, headers=auth_header)
    assert r2.status_code == 200
    data = r2.get_json()
    assert data["name"] == "New Name"
    assert data["balance"] == 2500.50


def test_update_account_type(client, auth_header):
    r = _create_account(client, auth_header, account_type="CHECKING")
    acct_id = r.get_json()["id"]
    r2 = client.patch(f"/accounts/{acct_id}", json={"account_type": "SAVINGS"}, headers=auth_header)
    assert r2.status_code == 200
    assert r2.get_json()["account_type"] == "SAVINGS"


def test_update_account_not_found(client, auth_header):
    r = client.patch("/accounts/99999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404


def test_delete_account(client, auth_header):
    r = _create_account(client, auth_header, name="Temp Account")
    acct_id = r.get_json()["id"]

    r2 = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r2.status_code == 200
    assert r2.get_json()["message"] == "deleted"

    r3 = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r3.status_code == 404


def test_delete_account_not_found(client, auth_header):
    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_accounts_isolated_between_users(client, app_fixture):
    """Two users should not see each other's accounts."""
    def _register_login(email, password):
        client.post("/auth/register", json={"email": email, "password": password})
        r = client.post("/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    h1 = _register_login("user1@test.com", "password123")
    h2 = _register_login("user2@test.com", "password123")

    _create_account(client, h1, name="User1 Account")
    _create_account(client, h2, name="User2 Account")

    r1 = client.get("/accounts", headers=h1)
    r2 = client.get("/accounts", headers=h2)

    names1 = [a["name"] for a in r1.get_json()]
    names2 = [a["name"] for a in r2.get_json()]

    assert "User1 Account" in names1
    assert "User2 Account" not in names1
    assert "User2 Account" in names2
    assert "User1 Account" not in names2


def test_all_account_types_accepted(client, auth_header):
    for atype in ("CHECKING", "SAVINGS", "CREDIT", "INVESTMENT", "CASH", "OTHER"):
        r = _create_account(client, auth_header, name=f"Test {atype}", account_type=atype)
        assert r.status_code == 201, f"Expected 201 for account_type={atype}, got {r.status_code}"
        assert r.get_json()["account_type"] == atype


# ---------------------------------------------------------------------------
# /dashboard/overview multi-account aggregation
# ---------------------------------------------------------------------------

def test_overview_empty(client, auth_header):
    r = client.get("/dashboard/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["net_worth"] == 0.0
    assert data["accounts"] == []
    assert data["account_summary_by_type"] == []
    assert data["recent_transactions"] == []
    assert data["spending_breakdown"] == []


def test_overview_net_worth_calculation(client, auth_header):
    """Net worth = checking + savings + investment - credit balance."""
    _create_account(client, auth_header, name="Checking", account_type="CHECKING", balance=2000)
    _create_account(client, auth_header, name="Savings", account_type="SAVINGS", balance=5000)
    _create_account(client, auth_header, name="Credit Card", account_type="CREDIT", balance=500)
    _create_account(client, auth_header, name="Stocks", account_type="INVESTMENT", balance=10000)

    r = client.get("/dashboard/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # 2000 + 5000 + 10000 - 500 = 16500
    assert data["net_worth"] == 16500.0
    assert len(data["accounts"]) == 4


def test_overview_account_summary_by_type(client, auth_header):
    _create_account(client, auth_header, name="Checking 1", account_type="CHECKING", balance=1000)
    _create_account(client, auth_header, name="Checking 2", account_type="CHECKING", balance=500)
    _create_account(client, auth_header, name="Savings", account_type="SAVINGS", balance=3000)

    r = client.get("/dashboard/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    by_type = {t["account_type"]: t["total_balance"] for t in data["account_summary_by_type"]}
    assert by_type["CHECKING"] == 1500.0
    assert by_type["SAVINGS"] == 3000.0


def test_overview_recent_transactions(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 150, "description": "Groceries", "date": date.today().isoformat(), "expense_type": "EXPENSE"},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 3000, "description": "Salary", "date": date.today().isoformat(), "expense_type": "INCOME"},
        headers=auth_header,
    )

    r = client.get("/dashboard/overview", headers=auth_header)
    assert r.status_code == 200
    txns = r.get_json()["recent_transactions"]
    descriptions = [t["description"] for t in txns]
    assert "Groceries" in descriptions
    assert "Salary" in descriptions


def test_overview_spending_breakdown_by_category(client, auth_header):
    r_cat = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    food_id = r_cat.get_json()["id"]

    today = date.today().isoformat()
    client.post(
        "/expenses",
        json={"amount": 200, "description": "Lunch", "date": today, "expense_type": "EXPENSE", "category_id": food_id},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 100, "description": "Dinner", "date": today, "expense_type": "EXPENSE", "category_id": food_id},
        headers=auth_header,
    )

    month = date.today().strftime("%Y-%m")
    r = client.get(f"/dashboard/overview?month={month}", headers=auth_header)
    assert r.status_code == 200
    breakdown = r.get_json()["spending_breakdown"]
    assert len(breakdown) >= 1
    food_entry = next((b for b in breakdown if b["category_name"] == "Food"), None)
    assert food_entry is not None
    assert food_entry["amount"] == 300.0
    assert food_entry["share_pct"] == 100.0


def test_overview_invalid_month_returns_400(client, auth_header):
    r = client.get("/dashboard/overview?month=not-a-month", headers=auth_header)
    assert r.status_code == 400


def test_overview_only_shows_active_accounts(client, auth_header):
    _create_account(client, auth_header, name="Active", balance=1000)
    r_inactive = _create_account(client, auth_header, name="Inactive", balance=9999)
    client.patch(
        f"/accounts/{r_inactive.get_json()['id']}",
        json={"is_active": False},
        headers=auth_header,
    )

    r = client.get("/dashboard/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    account_names = [a["name"] for a in data["accounts"]]
    assert "Active" in account_names
    assert "Inactive" not in account_names
    # net worth should not include the inactive account's 9999 balance
    assert data["net_worth"] == 1000.0
