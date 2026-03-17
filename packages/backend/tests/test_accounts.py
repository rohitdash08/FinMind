"""
Tests for multi-account financial overview — Issue #132.

Covers:
  - CRUD (create, list, get, update, delete)
  - balance computation
  - overview aggregation
  - user isolation
  - validation errors
"""

import pytest
from flask_jwt_extended import create_access_token
from app.models import User
from app.extensions import db


# Override conftest auth_header to bypass Redis (login stores refresh token in Redis)
@pytest.fixture()
def auth_header(client, app_fixture):
    with app_fixture.app_context():
        user = User(
            email="accttest@example.com",
            password_hash="x",
            preferred_currency="INR",
            role="USER",
        )
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _create(client, headers, **kwargs):
    payload = {"name": "Test Account", "account_type": "BANK", "currency": "INR", **kwargs}
    return client.post("/accounts", json=payload, headers=headers)


def _make_user(client, app_fixture, email="other@example.com"):
    """Create a second user directly (no Redis needed)."""
    from werkzeug.security import generate_password_hash
    with app_fixture.app_context():
        user = User(
            email=email,
            password_hash=generate_password_hash("pass1234"),
            preferred_currency="INR",
            role="USER",
        )
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateAccount:
    def test_create_minimal(self, client, auth_header):
        r = _create(client, auth_header, name="Savings")
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Savings"
        assert data["account_type"] == "BANK"
        assert data["currency"] == "INR"
        assert data["current_balance"] == 0.0
        assert data["active"] is True

    def test_create_with_initial_balance(self, client, auth_header):
        r = _create(client, auth_header, name="Wallet", initial_balance=5000, account_type="CASH")
        assert r.status_code == 201
        data = r.get_json()
        assert data["current_balance"] == 5000.0
        assert data["initial_balance"] == 5000.0

    def test_create_with_color(self, client, auth_header):
        r = _create(client, auth_header, name="CC", account_type="CREDIT", color="#FF5733")
        assert r.status_code == 201
        assert r.get_json()["color"] == "#FF5733"

    def test_create_missing_name(self, client, auth_header):
        r = client.post("/accounts", json={"account_type": "BANK"}, headers=auth_header)
        assert r.status_code == 400

    def test_create_invalid_type(self, client, auth_header):
        r = _create(client, auth_header, name="X", account_type="PONZI")
        assert r.status_code == 400

    def test_create_invalid_balance(self, client, auth_header):
        r = _create(client, auth_header, name="X", initial_balance="oops")
        assert r.status_code == 400

    def test_create_requires_auth(self, client):
        r = client.post("/accounts", json={"name": "X"})
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# List
# ─────────────────────────────────────────────────────────────────────────────

class TestListAccounts:
    def test_list_empty(self, client, auth_header):
        r = client.get("/accounts", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_returns_own_accounts(self, client, auth_header):
        _create(client, auth_header, name="Acct A")
        _create(client, auth_header, name="Acct B")
        r = client.get("/accounts", headers=auth_header)
        assert r.status_code == 200
        names = [a["name"] for a in r.get_json()]
        assert "Acct A" in names and "Acct B" in names

    def test_list_excludes_other_users(self, client, auth_header, app_fixture):
        other = _make_user(client, app_fixture, email="lx_intruder@ex.com")
        _create(client, other, name="Intruder Account")
        r = client.get("/accounts", headers=auth_header)
        names = [a["name"] for a in r.get_json()]
        assert "Intruder Account" not in names

    def test_list_requires_auth(self, client):
        r = client.get("/accounts")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Get detail
# ─────────────────────────────────────────────────────────────────────────────

class TestGetAccount:
    def test_get_own_account(self, client, auth_header):
        acct_id = _create(client, auth_header, name="Detail Test").get_json()["id"]
        r = client.get(f"/accounts/{acct_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["name"] == "Detail Test"

    def test_get_other_user_account_404(self, client, auth_header, app_fixture):
        other = _make_user(client, app_fixture, email="otherg@ex.com")
        other_id = _create(client, other, name="Others").get_json()["id"]
        r = client.get(f"/accounts/{other_id}", headers=auth_header)
        assert r.status_code == 404

    def test_get_nonexistent_404(self, client, auth_header):
        r = client.get("/accounts/999999", headers=auth_header)
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Update
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateAccount:
    def test_update_name(self, client, auth_header):
        acct_id = _create(client, auth_header, name="Old Name").get_json()["id"]
        r = client.patch(f"/accounts/{acct_id}", json={"name": "New Name"}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["name"] == "New Name"

    def test_update_type_and_currency(self, client, auth_header):
        acct_id = _create(client, auth_header, name="Test").get_json()["id"]
        r = client.patch(
            f"/accounts/{acct_id}",
            json={"account_type": "CREDIT", "currency": "USD"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["account_type"] == "CREDIT"
        assert data["currency"] == "USD"

    def test_update_empty_name_rejected(self, client, auth_header):
        acct_id = _create(client, auth_header, name="Ok").get_json()["id"]
        r = client.patch(f"/accounts/{acct_id}", json={"name": ""}, headers=auth_header)
        assert r.status_code == 400

    def test_update_other_user_account_404(self, client, auth_header, app_fixture):
        other = _make_user(client, app_fixture, email="otheru@ex.com")
        other_id = _create(client, other, name="Theirs").get_json()["id"]
        r = client.patch(f"/accounts/{other_id}", json={"name": "Mine"}, headers=auth_header)
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteAccount:
    def test_soft_delete(self, client, auth_header):
        acct_id = _create(client, auth_header, name="ToDelete").get_json()["id"]
        r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
        assert r.status_code == 204
        # Should no longer appear in list
        listing = client.get("/accounts", headers=auth_header).get_json()
        ids = [a["id"] for a in listing]
        assert acct_id not in ids

    def test_delete_other_user_404(self, client, auth_header, app_fixture):
        other = _make_user(client, app_fixture, email="otherd@ex.com")
        other_id = _create(client, other, name="Theirs").get_json()["id"]
        r = client.delete(f"/accounts/{other_id}", headers=auth_header)
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Overview
# ─────────────────────────────────────────────────────────────────────────────

class TestAccountsOverview:
    def test_overview_empty(self, client, auth_header):
        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_balance"] == 0.0
        assert data["accounts"] == []

    def test_overview_sums_initial_balances(self, client, auth_header):
        _create(client, auth_header, name="Savings", initial_balance=10000)
        _create(client, auth_header, name="Checking", initial_balance=5000)
        r = client.get("/accounts/overview", headers=auth_header)
        data = r.get_json()
        assert data["total_balance"] == 15000.0
        assert len(data["accounts"]) == 2

    def test_overview_includes_net_flow(self, client, auth_header):
        r = client.get("/accounts/overview", headers=auth_header)
        data = r.get_json()
        assert "net_flow" in data
        assert "total_income" in data
        assert "total_spent" in data

    def test_overview_requires_auth(self, client):
        r = client.get("/accounts/overview")
        assert r.status_code == 401

    def test_overview_excludes_other_users(self, client, auth_header, app_fixture):
        other = _make_user(client, app_fixture, email="ovo@ex.com")
        _create(client, other, name="Other", initial_balance=9999)
        # Our user has no accounts
        r = client.get("/accounts/overview", headers=auth_header)
        data = r.get_json()
        assert data["total_balance"] == 0.0
