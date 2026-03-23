"""Tests for financial accounts (multi-account dashboard) endpoints."""

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_account(client, auth_header, **kwargs):
    payload = {
        "name": "Main Checking",
        "account_type": "CHECKING",
        "balance": 1000.00,
        "currency": "INR",
    }
    payload.update(kwargs)
    return client.post("/accounts", json=payload, headers=auth_header)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


class TestCreateAccount:
    def test_create_basic(self, client, auth_header):
        r = _create_account(client, auth_header)
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Main Checking"
        assert data["account_type"] == "CHECKING"
        assert data["balance"] == 1000.0
        assert data["currency"] == "INR"
        assert data["active"] is True
        assert "id" in data

    def test_create_with_all_fields(self, client, auth_header):
        r = _create_account(
            client,
            auth_header,
            name="HDFC Savings",
            account_type="SAVINGS",
            balance=50000,
            currency="INR",
            institution="HDFC Bank",
            last_four="4321",
            color="#4f46e5",
            include_in_overview=True,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["institution"] == "HDFC Bank"
        assert data["last_four"] == "4321"
        assert data["color"] == "#4f46e5"

    def test_create_credit_card(self, client, auth_header):
        r = _create_account(
            client,
            auth_header,
            name="Axis Credit Card",
            account_type="CREDIT_CARD",
            balance=5000,  # outstanding balance
        )
        assert r.status_code == 201
        assert r.get_json()["account_type"] == "CREDIT_CARD"

    def test_create_missing_name_returns_400(self, client, auth_header):
        r = client.post(
            "/accounts",
            json={"account_type": "CHECKING", "balance": 100},
            headers=auth_header,
        )
        assert r.status_code == 400
        assert "name" in r.get_json()["error"]

    def test_create_invalid_account_type_returns_400(self, client, auth_header):
        r = client.post(
            "/accounts",
            json={"name": "Test", "account_type": "INVALID"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_create_invalid_balance_returns_400(self, client, auth_header):
        r = client.post(
            "/accounts",
            json={"name": "Test", "balance": "not_a_number"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_create_invalid_last_four_returns_400(self, client, auth_header):
        r = client.post(
            "/accounts",
            json={"name": "Test", "last_four": "123"},  # only 3 digits
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_requires_auth(self, client):
        r = client.post("/accounts", json={"name": "Test"})
        assert r.status_code == 401


class TestListAccounts:
    def test_list_empty(self, client, auth_header):
        r = client.get("/accounts", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_returns_created_accounts(self, client, auth_header):
        _create_account(client, auth_header, name="Acc A")
        _create_account(client, auth_header, name="Acc B")
        r = client.get("/accounts", headers=auth_header)
        assert r.status_code == 200
        names = [a["name"] for a in r.get_json()]
        assert "Acc A" in names
        assert "Acc B" in names

    def test_list_excludes_inactive_by_default(self, client, auth_header):
        r = _create_account(client, auth_header, name="Active")
        acc_id = r.get_json()["id"]
        # Deactivate it
        client.delete(f"/accounts/{acc_id}", headers=auth_header)
        r = client.get("/accounts", headers=auth_header)
        assert r.status_code == 200
        names = [a["name"] for a in r.get_json()]
        assert "Active" not in names

    def test_list_includes_inactive_when_flag_set(self, client, auth_header):
        r = _create_account(client, auth_header, name="Deactivated")
        acc_id = r.get_json()["id"]
        client.delete(f"/accounts/{acc_id}", headers=auth_header)
        r = client.get("/accounts?include_inactive=true", headers=auth_header)
        assert r.status_code == 200
        names = [a["name"] for a in r.get_json()]
        assert "Deactivated" in names

    def test_requires_auth(self, client):
        r = client.get("/accounts")
        assert r.status_code == 401


class TestGetAccount:
    def test_get_existing(self, client, auth_header):
        r = _create_account(client, auth_header, name="My Account")
        acc_id = r.get_json()["id"]
        r = client.get(f"/accounts/{acc_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["name"] == "My Account"

    def test_get_not_found(self, client, auth_header):
        r = client.get("/accounts/99999", headers=auth_header)
        assert r.status_code == 404

    def test_cannot_get_other_users_account(self, client, auth_header):
        # Create account for user1 then try to access as user2
        r = _create_account(client, auth_header, name="User1 Account")
        acc_id = r.get_json()["id"]

        # Register/login as user2
        client.post(
            "/auth/register", json={"email": "user2@example.com", "password": "pass2222"}
        )
        r2 = client.post(
            "/auth/login", json={"email": "user2@example.com", "password": "pass2222"}
        )
        token2 = r2.get_json()["access_token"]
        h2 = {"Authorization": f"Bearer {token2}"}

        r = client.get(f"/accounts/{acc_id}", headers=h2)
        assert r.status_code == 404


class TestUpdateAccount:
    def test_update_name(self, client, auth_header):
        acc_id = _create_account(client, auth_header).get_json()["id"]
        r = client.patch(
            f"/accounts/{acc_id}", json={"name": "Updated Name"}, headers=auth_header
        )
        assert r.status_code == 200
        assert r.get_json()["name"] == "Updated Name"

    def test_update_balance(self, client, auth_header):
        acc_id = _create_account(client, auth_header, balance=500).get_json()["id"]
        r = client.patch(
            f"/accounts/{acc_id}", json={"balance": 1500}, headers=auth_header
        )
        assert r.status_code == 200
        assert r.get_json()["balance"] == 1500.0

    def test_update_multiple_fields(self, client, auth_header):
        acc_id = _create_account(client, auth_header).get_json()["id"]
        r = client.patch(
            f"/accounts/{acc_id}",
            json={
                "name": "Renamed",
                "institution": "ICICI",
                "color": "#ff0000",
                "include_in_overview": False,
            },
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["institution"] == "ICICI"
        assert data["color"] == "#ff0000"
        assert data["include_in_overview"] is False

    def test_update_not_found(self, client, auth_header):
        r = client.patch(
            "/accounts/99999", json={"name": "Ghost"}, headers=auth_header
        )
        assert r.status_code == 404


class TestDeleteAccount:
    def test_soft_delete(self, client, auth_header):
        acc_id = _create_account(client, auth_header).get_json()["id"]
        r = client.delete(f"/accounts/{acc_id}", headers=auth_header)
        assert r.status_code == 200
        # Should not appear in default list
        r = client.get("/accounts", headers=auth_header)
        assert all(a["id"] != acc_id for a in r.get_json())
        # But the record still exists
        r = client.get(f"/accounts/{acc_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["active"] is False

    def test_delete_not_found(self, client, auth_header):
        r = client.delete("/accounts/99999", headers=auth_header)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Multi-account overview tests
# ---------------------------------------------------------------------------


class TestMultiAccountOverview:
    def test_overview_empty(self, client, auth_header):
        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "accounts" in data
        assert "totals" in data
        assert "monthly_summary" in data
        assert "upcoming_bills" in data
        assert "category_breakdown" in data

    def test_overview_totals_assets(self, client, auth_header):
        _create_account(client, auth_header, name="Savings", balance=10000, account_type="SAVINGS")
        _create_account(client, auth_header, name="Checking", balance=5000, account_type="CHECKING")

        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        totals = r.get_json()["totals"]
        assert totals["total_assets"] == 15000.0
        assert totals["total_liabilities"] == 0.0
        assert totals["net_worth"] == 15000.0

    def test_overview_totals_with_credit_card_liability(self, client, auth_header):
        _create_account(
            client, auth_header, name="Savings", balance=20000, account_type="SAVINGS"
        )
        _create_account(
            client,
            auth_header,
            name="CC",
            balance=5000,  # outstanding credit card balance = liability
            account_type="CREDIT_CARD",
        )

        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        totals = r.get_json()["totals"]
        assert totals["total_assets"] == 20000.0
        assert totals["total_liabilities"] == 5000.0
        assert totals["net_worth"] == 15000.0

    def test_overview_exclude_account(self, client, auth_header):
        _create_account(
            client,
            auth_header,
            name="Hidden",
            balance=999999,
            include_in_overview=False,
        )
        _create_account(
            client, auth_header, name="Visible", balance=1000, account_type="CHECKING"
        )

        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        totals = r.get_json()["totals"]
        # Hidden account should not contribute to totals
        assert totals["total_assets"] == 1000.0

    def test_overview_monthly_summary(self, client, auth_header):
        # Seed income and expense
        today = date.today().isoformat()
        client.post(
            "/expenses",
            json={"amount": 5000, "description": "Salary", "date": today, "expense_type": "INCOME"},
            headers=auth_header,
        )
        client.post(
            "/expenses",
            json={"amount": 1000, "description": "Rent", "date": today, "expense_type": "EXPENSE"},
            headers=auth_header,
        )

        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        ms = r.get_json()["monthly_summary"]
        assert ms["income"] >= 5000
        assert ms["expenses"] >= 1000
        assert ms["net_flow"] >= 4000

    def test_overview_upcoming_bills(self, client, auth_header):
        due = (date.today() + timedelta(days=5)).isoformat()
        client.post(
            "/bills",
            json={"name": "Netflix", "amount": 199, "next_due_date": due, "cadence": "MONTHLY"},
            headers=auth_header,
        )

        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        bills = r.get_json()["upcoming_bills"]
        assert any(b["name"] == "Netflix" for b in bills)

    def test_overview_invalid_month(self, client, auth_header):
        r = client.get("/accounts/overview?month=not-a-month", headers=auth_header)
        assert r.status_code == 400

    def test_overview_requires_auth(self, client):
        r = client.get("/accounts/overview")
        assert r.status_code == 401

    def test_overview_returns_all_accounts_list(self, client, auth_header):
        _create_account(client, auth_header, name="Alpha")
        _create_account(client, auth_header, name="Beta")
        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        names = [a["name"] for a in r.get_json()["accounts"]]
        assert "Alpha" in names
        assert "Beta" in names
