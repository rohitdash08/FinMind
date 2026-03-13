"""
Tests for Multi-account financial overview (Issue #132).

Covers:
- Account CRUD (create, list, get, update, delete/deactivate)
- Account types validation
- Overview endpoint: per-account balance, net worth, totals
- Expenses linked to accounts contribute to balance
- Unassigned expenses tracked separately
- Auth required on all endpoints
- Users cannot access each other's accounts
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Account, Expense
from datetime import date


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="acc@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _create_account(client, headers, **kwargs):
    payload = {"name": "Main Bank", "account_type": "BANK", "currency": "INR", **kwargs}
    return client.post("/accounts", json=payload, headers=headers)


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _seed_expense(app_fixture, user_id, account_id=None, amount=500, expense_type="EXPENSE"):
    with app_fixture.app_context():
        db.session.add(Expense(
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency="INR",
            notes="test",
            spent_at=date.today(),
            expense_type=expense_type,
            account_id=account_id,
        ))
        db.session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Account CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TestAccountCrud:
    def test_create_account(self, client, app_fixture):
        h = _auth(client, "ac1@test.com")
        r = _create_account(client, h, name="Savings", initial_balance=5000)
        assert r.status_code == 201
        d = r.get_json()
        assert d["name"] == "Savings"
        assert d["initial_balance"] == 5000.0
        assert d["active"] is True

    def test_create_account_missing_name(self, client, app_fixture):
        h = _auth(client, "ac2@test.com")
        r = client.post("/accounts", json={"account_type": "BANK"}, headers=h)
        assert r.status_code == 400
        assert "name" in r.get_json()["error"]

    def test_create_account_invalid_type(self, client, app_fixture):
        h = _auth(client, "ac3@test.com")
        r = _create_account(client, h, account_type="BITCOIN")
        assert r.status_code == 400

    def test_list_accounts_empty(self, client, app_fixture):
        h = _auth(client, "ac4@test.com")
        r = client.get("/accounts", headers=h)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_accounts_own_only(self, client, app_fixture):
        h1 = _auth(client, "ac5a@test.com")
        h2 = _auth(client, "ac5b@test.com")
        _create_account(client, h1, name="A")
        _create_account(client, h2, name="B")
        accounts = client.get("/accounts", headers=h1).get_json()
        assert len(accounts) == 1
        assert accounts[0]["name"] == "A"

    def test_get_account(self, client, app_fixture):
        h = _auth(client, "ac6@test.com")
        aid = _create_account(client, h).get_json()["id"]
        r = client.get(f"/accounts/{aid}", headers=h)
        assert r.status_code == 200
        assert r.get_json()["id"] == aid

    def test_get_account_other_user_forbidden(self, client, app_fixture):
        h1 = _auth(client, "ac7a@test.com")
        h2 = _auth(client, "ac7b@test.com")
        aid = _create_account(client, h1).get_json()["id"]
        assert client.get(f"/accounts/{aid}", headers=h2).status_code == 404

    def test_update_account(self, client, app_fixture):
        h = _auth(client, "ac8@test.com")
        aid = _create_account(client, h, name="Old").get_json()["id"]
        r = client.patch(f"/accounts/{aid}", json={"name": "New", "color": "#ff0000"}, headers=h)
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"
        assert r.get_json()["color"] == "#ff0000"

    def test_update_account_invalid_type(self, client, app_fixture):
        h = _auth(client, "ac9@test.com")
        aid = _create_account(client, h).get_json()["id"]
        r = client.patch(f"/accounts/{aid}", json={"account_type": "INVALID"}, headers=h)
        assert r.status_code == 400

    def test_delete_account_deactivates(self, client, app_fixture):
        h = _auth(client, "ac10@test.com")
        aid = _create_account(client, h).get_json()["id"]
        r = client.delete(f"/accounts/{aid}", headers=h)
        assert r.status_code == 200
        # Should not appear in list anymore
        accounts = client.get("/accounts", headers=h).get_json()
        assert not any(a["id"] == aid for a in accounts)

    def test_all_endpoints_require_auth(self, client, app_fixture):
        assert client.get("/accounts").status_code == 401
        assert client.post("/accounts", json={}).status_code == 401
        assert client.get("/accounts/overview").status_code == 401
        assert client.get("/accounts/1").status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Overview
# ─────────────────────────────────────────────────────────────────────────────

class TestAccountOverview:
    def test_overview_empty(self, client, app_fixture):
        h = _auth(client, "ov1@test.com")
        r = client.get("/accounts/overview", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert d["accounts"] == []
        assert d["summary"]["net_worth"] == 0.0
        assert d["summary"]["account_count"] == 0

    def test_overview_with_initial_balance(self, client, app_fixture):
        h = _auth(client, "ov2@test.com")
        _create_account(client, h, name="Bank", initial_balance=10000)
        r = client.get("/accounts/overview", headers=h)
        d = r.get_json()
        assert d["summary"]["total_assets"] == 10000.0
        assert d["summary"]["net_worth"] == 10000.0

    def test_overview_expenses_reduce_balance(self, client, app_fixture):
        h = _auth(client, "ov3@test.com")
        uid = _get_uid(app_fixture, "ov3@test.com")
        aid = _create_account(client, h, name="Bank", initial_balance=10000).get_json()["id"]
        _seed_expense(app_fixture, uid, account_id=aid, amount=2000, expense_type="EXPENSE")

        r = client.get("/accounts/overview", headers=h)
        acc = r.get_json()["accounts"][0]
        assert acc["balance"] == 8000.0
        assert acc["expenses"] == 2000.0

    def test_overview_income_increases_balance(self, client, app_fixture):
        h = _auth(client, "ov4@test.com")
        uid = _get_uid(app_fixture, "ov4@test.com")
        aid = _create_account(client, h, name="Bank", initial_balance=0).get_json()["id"]
        _seed_expense(app_fixture, uid, account_id=aid, amount=5000, expense_type="INCOME")

        r = client.get("/accounts/overview", headers=h)
        acc = r.get_json()["accounts"][0]
        assert acc["balance"] == 5000.0
        assert acc["income"] == 5000.0

    def test_overview_credit_is_liability(self, client, app_fixture):
        h = _auth(client, "ov5@test.com")
        _create_account(client, h, name="CC", account_type="CREDIT", initial_balance=1000)
        r = client.get("/accounts/overview", headers=h)
        s = r.get_json()["summary"]
        assert s["total_liabilities"] == 1000.0
        assert s["total_assets"] == 0.0
        assert s["net_worth"] == -1000.0

    def test_overview_unassigned_expenses(self, client, app_fixture):
        h = _auth(client, "ov6@test.com")
        uid = _get_uid(app_fixture, "ov6@test.com")
        _seed_expense(app_fixture, uid, account_id=None, amount=300, expense_type="EXPENSE")

        r = client.get("/accounts/overview", headers=h)
        s = r.get_json()["summary"]
        assert s["unassigned_expenses"] == 300.0

    def test_overview_multiple_accounts(self, client, app_fixture):
        h = _auth(client, "ov7@test.com")
        _create_account(client, h, name="Bank", initial_balance=5000)
        _create_account(client, h, name="Cash", account_type="CASH", initial_balance=500)
        _create_account(client, h, name="CC", account_type="CREDIT", initial_balance=2000)

        r = client.get("/accounts/overview", headers=h)
        d = r.get_json()
        assert d["summary"]["account_count"] == 3
        assert d["summary"]["total_assets"] == 5500.0
        assert d["summary"]["total_liabilities"] == 2000.0
        assert d["summary"]["net_worth"] == 3500.0
