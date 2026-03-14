"""Tests for financial accounts CRUD and multi-account overview."""

import pytest


# ── helpers ────────────────────────────────────────────────────────────
def _register_and_login(client, email="acct@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_account(client, headers, **overrides):
    payload = {
        "name": "Main Checking",
        "account_type": "BANK",
        "currency": "USD",
        "balance": 5000.00,
        "institution": "Chase",
        "last_four": "4321",
        "color": "#10B981",
    }
    payload.update(overrides)
    return client.post("/accounts", json=payload, headers=headers)


# ── CREATE ─────────────────────────────────────────────────────────────
class TestCreateAccount:
    def test_create_minimal(self, client):
        h = _register_and_login(client, "min@test.com")
        r = _create_account(client, h, name="Simple", balance=0)
        assert r.status_code == 201
        d = r.get_json()
        assert d["name"] == "Simple"
        assert d["active"] is True
        assert d["id"] > 0

    def test_create_with_all_fields(self, client):
        h = _register_and_login(client, "full@test.com")
        r = _create_account(client, h)
        assert r.status_code == 201
        d = r.get_json()
        assert d["name"] == "Main Checking"
        assert d["account_type"] == "BANK"
        assert d["currency"] == "USD"
        assert d["balance"] == 5000.00
        assert d["institution"] == "Chase"
        assert d["last_four"] == "4321"
        assert d["color"] == "#10B981"

    def test_create_with_initial_balance(self, client):
        h = _register_and_login(client, "bal@test.com")
        r = _create_account(client, h, balance=12345.67)
        assert r.status_code == 201
        assert r.get_json()["balance"] == 12345.67

    def test_create_invalid_name_empty(self, client):
        h = _register_and_login(client, "err1@test.com")
        r = _create_account(client, h, name="")
        assert r.status_code == 400
        assert "name" in r.get_json()["error"]

    def test_create_invalid_type(self, client):
        h = _register_and_login(client, "err2@test.com")
        r = _create_account(client, h, account_type="INVALID")
        assert r.status_code == 400
        assert "account_type" in r.get_json()["error"]

    def test_create_requires_auth(self, client):
        r = client.post("/accounts", json={"name": "No Auth"})
        assert r.status_code in (401, 422)


# ── LIST ───────────────────────────────────────────────────────────────
class TestListAccounts:
    def test_list_empty(self, client):
        h = _register_and_login(client, "empty@test.com")
        r = client.get("/accounts", headers=h)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_own_accounts(self, client):
        h = _register_and_login(client, "own@test.com")
        _create_account(client, h, name="A1")
        _create_account(client, h, name="A2")
        r = client.get("/accounts", headers=h)
        assert r.status_code == 200
        names = [a["name"] for a in r.get_json()]
        assert "A1" in names
        assert "A2" in names

    def test_list_user_isolation(self, client):
        h1 = _register_and_login(client, "u1@test.com")
        h2 = _register_and_login(client, "u2@test.com")
        _create_account(client, h1, name="User1 Acct")
        _create_account(client, h2, name="User2 Acct")
        r1 = client.get("/accounts", headers=h1)
        names1 = [a["name"] for a in r1.get_json()]
        assert "User1 Acct" in names1
        assert "User2 Acct" not in names1

    def test_list_requires_auth(self, client):
        r = client.get("/accounts")
        assert r.status_code in (401, 422)


# ── GET ────────────────────────────────────────────────────────────────
class TestGetAccount:
    def test_get_own(self, client):
        h = _register_and_login(client, "get@test.com")
        cr = _create_account(client, h, name="GetMe")
        aid = cr.get_json()["id"]
        r = client.get(f"/accounts/{aid}", headers=h)
        assert r.status_code == 200
        assert r.get_json()["name"] == "GetMe"

    def test_get_404_other_user(self, client):
        h1 = _register_and_login(client, "g1@test.com")
        h2 = _register_and_login(client, "g2@test.com")
        cr = _create_account(client, h1, name="Private")
        aid = cr.get_json()["id"]
        r = client.get(f"/accounts/{aid}", headers=h2)
        assert r.status_code == 404

    def test_get_404_nonexistent(self, client):
        h = _register_and_login(client, "ne@test.com")
        r = client.get("/accounts/99999", headers=h)
        assert r.status_code == 404


# ── UPDATE ─────────────────────────────────────────────────────────────
class TestUpdateAccount:
    def test_update_name(self, client):
        h = _register_and_login(client, "upd@test.com")
        cr = _create_account(client, h, name="Old")
        aid = cr.get_json()["id"]
        r = client.patch(f"/accounts/{aid}", json={"name": "New"}, headers=h)
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"

    def test_update_type_and_currency(self, client):
        h = _register_and_login(client, "updt@test.com")
        cr = _create_account(client, h)
        aid = cr.get_json()["id"]
        r = client.patch(
            f"/accounts/{aid}",
            json={"account_type": "CREDIT", "currency": "EUR"},
            headers=h,
        )
        assert r.status_code == 200
        d = r.get_json()
        assert d["account_type"] == "CREDIT"
        assert d["currency"] == "EUR"

    def test_update_empty_name_rejected(self, client):
        h = _register_and_login(client, "updnm@test.com")
        cr = _create_account(client, h)
        aid = cr.get_json()["id"]
        r = client.patch(f"/accounts/{aid}", json={"name": ""}, headers=h)
        assert r.status_code == 400

    def test_update_404_other_user(self, client):
        h1 = _register_and_login(client, "up1@test.com")
        h2 = _register_and_login(client, "up2@test.com")
        cr = _create_account(client, h1)
        aid = cr.get_json()["id"]
        r = client.patch(f"/accounts/{aid}", json={"name": "Hacked"}, headers=h2)
        assert r.status_code == 404


# ── DELETE ─────────────────────────────────────────────────────────────
class TestDeleteAccount:
    def test_soft_delete(self, client):
        h = _register_and_login(client, "del@test.com")
        cr = _create_account(client, h, name="ToDelete")
        aid = cr.get_json()["id"]
        r = client.delete(f"/accounts/{aid}", headers=h)
        assert r.status_code == 200
        # Should not appear in list anymore
        r2 = client.get("/accounts", headers=h)
        ids = [a["id"] for a in r2.get_json()]
        assert aid not in ids

    def test_delete_404_other_user(self, client):
        h1 = _register_and_login(client, "d1@test.com")
        h2 = _register_and_login(client, "d2@test.com")
        cr = _create_account(client, h1)
        aid = cr.get_json()["id"]
        r = client.delete(f"/accounts/{aid}", headers=h2)
        assert r.status_code == 404


# ── OVERVIEW ───────────────────────────────────────────────────────────
class TestAccountsOverview:
    def test_overview_empty(self, client):
        h = _register_and_login(client, "ov@test.com")
        r = client.get("/accounts/overview", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert d["total_accounts"] == 0
        assert d["net_worth"] == 0
        assert d["accounts"] == []

    def test_overview_balance_aggregation(self, client):
        h = _register_and_login(client, "ovb@test.com")
        _create_account(client, h, name="Checking", balance=10000, account_type="BANK")
        _create_account(client, h, name="Savings", balance=5000, account_type="BANK")
        _create_account(client, h, name="Credit Card", balance=2000, account_type="CREDIT")
        r = client.get("/accounts/overview", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert d["total_accounts"] == 3
        assert d["total_assets"] == 15000.0
        assert d["total_liabilities"] == 2000.0
        assert d["net_worth"] == 13000.0

    def test_overview_by_type(self, client):
        h = _register_and_login(client, "ovt@test.com")
        _create_account(client, h, name="B1", account_type="BANK", balance=100)
        _create_account(client, h, name="B2", account_type="BANK", balance=200)
        _create_account(client, h, name="C1", account_type="CASH", balance=50)
        r = client.get("/accounts/overview", headers=h)
        d = r.get_json()
        assert d["by_type"]["BANK"]["count"] == 2
        assert d["by_type"]["BANK"]["total_balance"] == 300.0
        assert d["by_type"]["CASH"]["count"] == 1

    def test_overview_requires_auth(self, client):
        r = client.get("/accounts/overview")
        assert r.status_code in (401, 422)

    def test_overview_user_isolation(self, client):
        h1 = _register_and_login(client, "ovi1@test.com")
        h2 = _register_and_login(client, "ovi2@test.com")
        _create_account(client, h1, name="User1 Only", balance=999)
        r2 = client.get("/accounts/overview", headers=h2)
        assert r2.get_json()["total_accounts"] == 0
