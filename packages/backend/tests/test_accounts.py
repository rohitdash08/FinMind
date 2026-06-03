"""Tests for the multi-account dashboard feature (#132)."""
import pytest
from app.extensions import db
from app.models import User
from app.routes.accounts import FinancialAccount, AccountType


@pytest.fixture
def seed_user(app):
    with app.app_context():
        user = User(email="accounts-test@test.com", password_hash="hash", preferred_currency="USD")
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def seed_accounts(app, seed_user):
    with app.app_context():
        user = seed_user
        accounts = [
            FinancialAccount(user_id=user.id, name="Main Checking",
                             account_type="CHECKING", balance=5000.00),
            FinancialAccount(user_id=user.id, name="High-Yield Savings",
                             account_type="SAVINGS", balance=15000.00),
            FinancialAccount(user_id=user.id, name="Credit Card",
                             account_type="CREDIT", balance=-1200.00),
            FinancialAccount(user_id=user.id, name="Investment Portfolio",
                             account_type="INVESTMENT", balance=50000.00),
        ]
        for a in accounts:
            db.session.add(a)
        db.session.commit()
        yield user, accounts


class TestMultiAccount:
    """Tests for multi-account financial dashboard."""

    def test_list_accounts_empty(self, client, seed_user):
        resp = client.get(f"/api/accounts?user_id={seed_user.id}")
        assert resp.status_code == 200
        assert resp.json["accounts"] == []

    def test_create_account(self, client, seed_user):
        resp = client.post("/api/accounts", json={
            "user_id": seed_user.id,
            "name": "Test Account",
            "account_type": "CHECKING",
            "balance": 1000,
            "institution": "Test Bank",
        })
        assert resp.status_code == 201
        assert resp.json["name"] == "Test Account"
        assert resp.json["balance"] == 1000.0
        assert resp.json["account_type"] == "CHECKING"

    def test_create_account_requires_fields(self, client, seed_user):
        resp = client.post("/api/accounts", json={"user_id": seed_user.id})
        assert resp.status_code == 400

    def test_update_balance(self, client, seed_user):
        cr = client.post("/api/accounts", json={
            "user_id": seed_user.id, "name": "Update Test", "account_type": "SAVINGS", "balance": 500,
        })
        acc_id = cr.json["id"]
        resp = client.patch(f"/api/accounts/{acc_id}/balance", json={"balance": 750})
        assert resp.json["balance"] == 750.0

    def test_delete_account_soft(self, client, seed_user):
        cr = client.post("/api/accounts", json={
            "user_id": seed_user.id, "name": "Delete Me", "account_type": "CASH", "balance": 100,
        })
        acc_id = cr.json["id"]
        resp = client.delete(f"/api/accounts/{acc_id}")
        assert resp.status_code == 200
        # Verify it's deactivated
        get_resp = client.get(f"/api/accounts?user_id={seed_user.id}")
        ids = [a["id"] for a in get_resp.json["accounts"]]
        assert acc_id not in ids

    def test_dashboard_total(self, client, seed_accounts):
        user, _ = seed_accounts
        resp = client.get(f"/api/accounts/dashboard?user_id={user.id}")
        assert resp.status_code == 200
        # Checking 5000 + Savings 15000 + Credit -1200 + Investment 50000 = 68800
        assert resp.json["total_balance"] == 68800.0
        assert resp.json["total_accounts"] == 4

    def test_dashboard_breakdown_types(self, client, seed_accounts):
        user, _ = seed_accounts
        resp = client.get(f"/api/accounts/dashboard?user_id={user.id}")
        types = {b["type"] for b in resp.json["breakdown"]}
        assert types == {"CHECKING", "SAVINGS", "CREDIT", "INVESTMENT"}
