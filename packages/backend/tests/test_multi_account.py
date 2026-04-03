"""
Tests for multi-account financial overview.
Issue #132: Verify account CRUD and multi-account overview endpoint.
"""

import pytest
from datetime import datetime


class TestFinancialAccountModel:
    def test_account_model_exists(self):
        from packages.backend.app.models import FinancialAccount
        assert FinancialAccount is not None

    def test_account_type_constants_exist(self):
        from packages.backend.app.models import ACCOUNT_TYPES
        assert "checking" in ACCOUNT_TYPES
        assert "savings" in ACCOUNT_TYPES
        assert "credit_card" in ACCOUNT_TYPES
        assert "investment" in ACCOUNT_TYPES
        assert "cash" in ACCOUNT_TYPES

    def test_to_dict_returns_expected_fields(self):
        from packages.backend.app.models import FinancialAccount
        acc = FinancialAccount()
        acc.id = 1
        acc.name = "Test Account"
        acc.account_type = "checking"
        acc.currency = "USD"
        acc.opening_balance = 1000.00
        acc.is_active = True
        acc.color = "#123456"
        acc.icon = "bank"
        acc.created_at = datetime(2026, 4, 3)
        d = acc.to_dict()
        assert d["id"] == 1
        assert d["name"] == "Test Account"
        assert d["account_type"] == "checking"
        assert d["currency"] == "USD"
        assert d["opening_balance"] == 1000.00
        assert d["is_active"] is True

    def test_migration_file_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/009_multi_account.sql"
        )
        assert os.path.exists(path)


class TestAccountsEndpoints:
    def test_list_accounts_returns_200(self, client, auth_headers):
        response = client.get("/api/accounts", headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "accounts" in data
        assert isinstance(data["accounts"], list)

    def test_create_account_returns_201(self, client, auth_headers):
        response = client.post(
            "/api/accounts",
            json={
                "name": "My Checking",
                "account_type": "checking",
                "currency": "USD",
                "opening_balance": 5000.00,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.get_json()
        assert "account" in data
        assert data["account"]["name"] == "My Checking"

    def test_create_account_invalid_type_returns_400(self, client, auth_headers):
        response = client.post(
            "/api/accounts",
            json={"name": "Bad Account", "account_type": "invalid_type"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_create_account_requires_name(self, client, auth_headers):
        response = client.post(
            "/api/accounts",
            json={"account_type": "savings"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_get_account_returns_200(self, client, auth_headers, sample_account):
        response = client.get(f"/api/accounts/{sample_account['id']}", headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "account" in data
        assert "summary" in data

    def test_get_nonexistent_account_returns_404(self, client, auth_headers):
        response = client.get("/api/accounts/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_update_account_returns_200(self, client, auth_headers, sample_account):
        response = client.patch(
            f"/api/accounts/{sample_account['id']}",
            json={"name": "Updated Name", "color": "#ff0000"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["account"]["name"] == "Updated Name"
        assert data["account"]["color"] == "#ff0000"

    def test_delete_account_returns_200(self, client, auth_headers, sample_account):
        response = client.delete(
            f"/api/accounts/{sample_account['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_deleted_account_not_in_list(self, client, auth_headers, sample_account):
        client.delete(f"/api/accounts/{sample_account['id']}", headers=auth_headers)
        response = client.get("/api/accounts", headers=auth_headers)
        accounts = response.get_json()["accounts"]
        ids = [a["id"] for a in accounts]
        assert sample_account["id"] not in ids

    def test_overview_returns_200(self, client, auth_headers):
        response = client.get("/api/accounts/overview", headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "accounts" in data
        assert "totals" in data
        assert "period" in data

    def test_overview_totals_structure(self, client, auth_headers):
        response = client.get("/api/accounts/overview?month=2026-04", headers=auth_headers)
        assert response.status_code == 200
        totals = response.get_json()["totals"]
        assert "total_accounts" in totals
        assert "total_income" in totals
        assert "total_expenses" in totals
        assert "net_flow" in totals

    def test_overview_invalid_month_returns_400(self, client, auth_headers):
        response = client.get("/api/accounts/overview?month=invalid", headers=auth_headers)
        assert response.status_code == 400

    def test_all_endpoints_require_auth(self, client):
        for method, url in [
            ("GET", "/api/accounts"),
            ("POST", "/api/accounts"),
            ("GET", "/api/accounts/1"),
            ("PATCH", "/api/accounts/1"),
            ("DELETE", "/api/accounts/1"),
            ("GET", "/api/accounts/overview"),
        ]:
            response = getattr(client, method.lower())(url)
            assert response.status_code == 401, f"{method} {url} should require auth"