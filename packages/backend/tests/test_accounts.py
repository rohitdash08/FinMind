"""Tests for multi-account financial overview (#132)."""

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

ACCOUNT_PAYLOAD = {
    "name": "Main Checking",
    "account_type": "CHECKING",
    "currency": "INR",
    "initial_balance": 10000.0,
    "color": "#4CAF50",
}


def _create_account(client, auth_header, **overrides):
    payload = {**ACCOUNT_PAYLOAD, **overrides}
    return client.post("/accounts", json=payload, headers=auth_header)


# ── list / create ─────────────────────────────────────────────────────────────


def test_list_accounts_empty(client, auth_header):
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_account(client, auth_header):
    r = _create_account(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Main Checking"
    assert data["account_type"] == "CHECKING"
    assert data["initial_balance"] == 10000.0
    assert data["current_balance"] == 10000.0
    assert "id" in data


def test_create_account_default_type(client, auth_header):
    r = client.post("/accounts", json={"name": "Cash Wallet"}, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["account_type"] == "CHECKING"


def test_create_account_invalid_type(client, auth_header):
    r = _create_account(client, auth_header, account_type="INVALID")
    assert r.status_code == 400


def test_create_account_missing_name(client, auth_header):
    r = client.post("/accounts", json={"account_type": "SAVINGS"}, headers=auth_header)
    assert r.status_code == 400


def test_list_accounts_returns_all_active(client, auth_header):
    _create_account(client, auth_header, name="Acc 1")
    _create_account(client, auth_header, name="Acc 2", account_type="SAVINGS")
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    names = [a["name"] for a in r.get_json()]
    assert "Acc 1" in names
    assert "Acc 2" in names


# ── get single account ────────────────────────────────────────────────────────


def test_get_account_detail(client, auth_header):
    aid = _create_account(client, auth_header).get_json()["id"]
    r = client.get(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == aid
    assert "recent_transactions" in data
    assert isinstance(data["recent_transactions"], list)


def test_get_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


# ── update ────────────────────────────────────────────────────────────────────


def test_update_account_name(client, auth_header):
    aid = _create_account(client, auth_header).get_json()["id"]
    r = client.patch(f"/accounts/{aid}", json={"name": "Renamed"}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Renamed"


def test_update_account_invalid_type(client, auth_header):
    aid = _create_account(client, auth_header).get_json()["id"]
    r = client.patch(f"/accounts/{aid}", json={"account_type": "BOGUS"}, headers=auth_header)
    assert r.status_code == 400


# ── delete (soft) ──────────────────────────────────────────────────────────────


def test_delete_account(client, auth_header):
    aid = _create_account(client, auth_header).get_json()["id"]
    r = client.delete(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200
    # should no longer appear in list
    accounts = client.get("/accounts", headers=auth_header).get_json()
    assert all(a["id"] != aid for a in accounts)


def test_delete_account_not_found(client, auth_header):
    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


# ── overview ──────────────────────────────────────────────────────────────────


def test_overview_no_accounts(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["net_worth"] == 0
    assert data["account_count"] == 0


def test_overview_with_accounts(client, auth_header):
    _create_account(client, auth_header, name="Checking", initial_balance=5000, account_type="CHECKING")
    _create_account(client, auth_header, name="Savings", initial_balance=20000, account_type="SAVINGS")
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["account_count"] == 2
    assert data["net_worth"] == pytest.approx(25000.0)
    assert "CHECKING" in data["by_type"]
    assert "SAVINGS" in data["by_type"]


def test_overview_credit_reduces_net_worth(client, auth_header):
    _create_account(client, auth_header, name="Bank", initial_balance=10000, account_type="CHECKING")
    # Credit with negative initial_balance = outstanding debt
    _create_account(client, auth_header, name="Credit Card", initial_balance=-3000, account_type="CREDIT")
    r = client.get("/accounts/overview", headers=auth_header)
    data = r.get_json()
    # net_worth = assets(10000) - liabilities(3000) = 7000
    assert data["net_worth"] == pytest.approx(7000.0)


def test_unauthorized_access(client):
    r = client.get("/accounts")
    assert r.status_code == 401

    r = client.get("/accounts/overview")
    assert r.status_code == 401
