"""Tests for multi-account financial overview feature (#132)."""


class TestAccountCRUD:
    def test_create_account(self, client, auth_header):
        r = client.post(
            "/api/accounts",
            json={
                "name": "HDFC Savings",
                "account_type": "BANK",
                "initial_balance": 50000,
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "HDFC Savings"
        assert data["account_type"] == "BANK"
        assert data["initial_balance"] == 50000

    def test_create_account_invalid_type(self, client, auth_header):
        r = client.post(
            "/api/accounts",
            json={"name": "Bad", "account_type": "INVALID"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_create_account_no_name(self, client, auth_header):
        r = client.post(
            "/api/accounts",
            json={"name": "", "account_type": "BANK"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_list_accounts(self, client, auth_header):
        client.post(
            "/api/accounts",
            json={"name": "Account A", "account_type": "BANK"},
            headers=auth_header,
        )
        client.post(
            "/api/accounts",
            json={"name": "Account B", "account_type": "CREDIT_CARD"},
            headers=auth_header,
        )
        r = client.get("/api/accounts", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) >= 2

    def test_get_account(self, client, auth_header):
        r = client.post(
            "/api/accounts",
            json={
                "name": "My Savings",
                "account_type": "SAVINGS",
                "initial_balance": 10000,
            },
            headers=auth_header,
        )
        aid = r.get_json()["id"]
        r = client.get(f"/api/accounts/{aid}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["name"] == "My Savings"
        assert data["current_balance"] == 10000  # no transactions yet

    def test_update_account(self, client, auth_header):
        r = client.post(
            "/api/accounts",
            json={"name": "Old", "account_type": "CASH"},
            headers=auth_header,
        )
        aid = r.get_json()["id"]
        r = client.patch(
            f"/api/accounts/{aid}",
            json={"name": "Updated Cash"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["name"] == "Updated Cash"

    def test_delete_account(self, client, auth_header):
        r = client.post(
            "/api/accounts",
            json={"name": "Delete Me", "account_type": "OTHER"},
            headers=auth_header,
        )
        aid = r.get_json()["id"]
        r = client.delete(f"/api/accounts/{aid}", headers=auth_header)
        assert r.status_code == 204

        # Should be inactive now
        r = client.get(f"/api/accounts/{aid}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["is_active"] is False

    def test_get_nonexistent_account(self, client, auth_header):
        r = client.get("/api/accounts/99999", headers=auth_header)
        assert r.status_code == 404


class TestMultiAccountOverview:
    def test_overview_no_accounts(self, client, auth_header):
        r = client.get("/api/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_balance"] == 0
        assert data["accounts"] == []

    def test_overview_with_accounts(self, client, auth_header):
        client.post(
            "/api/accounts",
            json={
                "name": "Checking",
                "account_type": "BANK",
                "initial_balance": 5000,
            },
            headers=auth_header,
        )
        client.post(
            "/api/accounts",
            json={
                "name": "Savings",
                "account_type": "SAVINGS",
                "initial_balance": 20000,
            },
            headers=auth_header,
        )

        r = client.get("/api/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_balance"] == 25000
        assert data["account_count"] == 2
        assert len(data["accounts"]) == 2


class TestAccountTransactions:
    def test_list_transactions_empty(self, client, auth_header):
        r = client.post(
            "/api/accounts",
            json={"name": "Txn Test", "account_type": "BANK"},
            headers=auth_header,
        )
        aid = r.get_json()["id"]
        r = client.get(f"/api/accounts/{aid}/transactions", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 0
        assert data["transactions"] == []

    def test_transactions_nonexistent_account(self, client, auth_header):
        r = client.get("/api/accounts/99999/transactions", headers=auth_header)
        assert r.status_code == 404
