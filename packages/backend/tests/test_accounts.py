"""Tests for multi-account financial overview."""


class TestAccountsCRUD:
    def test_create_account(self, client, auth_header):
        r = client.post(
            "/accounts/",
            json={
                "name": "Main Checking",
                "account_type": "checking",
                "balance": 5000,
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Main Checking"
        assert data["balance"] == 5000
        assert data["is_active"]

    def test_create_invalid_type(self, client, auth_header):
        r = client.post(
            "/accounts/",
            json={"name": "Bad", "account_type": "invalid"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_create_missing_fields(self, client, auth_header):
        r = client.post("/accounts/", json={"name": "No Type"}, headers=auth_header)
        assert r.status_code == 400

    def test_list_accounts(self, client, auth_header):
        client.post(
            "/accounts/",
            json={"name": "A1", "account_type": "checking"},
            headers=auth_header,
        )
        client.post(
            "/accounts/",
            json={"name": "A2", "account_type": "savings"},
            headers=auth_header,
        )

        r = client.get("/accounts/", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_get_account(self, client, auth_header):
        r = client.post(
            "/accounts/",
            json={"name": "Test", "account_type": "cash"},
            headers=auth_header,
        )
        aid = r.get_json()["id"]

        r = client.get(f"/accounts/{aid}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["account_type"] == "cash"

    def test_update_account(self, client, auth_header):
        r = client.post(
            "/accounts/",
            json={"name": "Old", "account_type": "checking"},
            headers=auth_header,
        )
        aid = r.get_json()["id"]

        r = client.put(
            f"/accounts/{aid}",
            json={"name": "New", "balance": 999},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"
        assert r.get_json()["balance"] == 999

    def test_deactivate_account(self, client, auth_header):
        r = client.post(
            "/accounts/",
            json={"name": "Bye", "account_type": "savings"},
            headers=auth_header,
        )
        aid = r.get_json()["id"]

        r = client.delete(f"/accounts/{aid}", headers=auth_header)
        assert r.status_code == 200

        # Should not appear in active-only list
        r = client.get("/accounts/", headers=auth_header)
        assert len(r.get_json()) == 0

        # But appears with include_inactive
        r = client.get("/accounts/?include_inactive=true", headers=auth_header)
        assert len(r.get_json()) == 1


class TestOverview:
    def test_empty_overview(self, client, auth_header):
        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_balance"] == 0
        assert data["account_count"] == 0

    def test_overview_with_accounts(self, client, auth_header):
        client.post(
            "/accounts/",
            json={"name": "Checking", "account_type": "checking", "balance": 3000},
            headers=auth_header,
        )
        client.post(
            "/accounts/",
            json={"name": "Savings", "account_type": "savings", "balance": 10000},
            headers=auth_header,
        )
        client.post(
            "/accounts/",
            json={"name": "Credit Card", "account_type": "credit", "balance": 2000},
            headers=auth_header,
        )

        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_balance"] == 15000
        assert data["net_worth"] == 11000  # (3000 + 10000) - 2000
        assert data["account_count"] == 3
        assert "checking" in data["by_type"]
        assert "savings" in data["by_type"]
        assert "credit" in data["by_type"]
        assert len(data["accounts"]) == 3

    def test_overview_excludes_inactive(self, client, auth_header):
        r = client.post(
            "/accounts/",
            json={"name": "Active", "account_type": "checking", "balance": 1000},
            headers=auth_header,
        )
        active_id = r.get_json()["id"]

        r = client.post(
            "/accounts/",
            json={"name": "Inactive", "account_type": "savings", "balance": 5000},
            headers=auth_header,
        )
        inactive_id = r.get_json()["id"]
        client.delete(f"/accounts/{inactive_id}", headers=auth_header)

        r = client.get("/accounts/overview", headers=auth_header)
        data = r.get_json()
        assert data["total_balance"] == 1000
        assert data["account_count"] == 1
