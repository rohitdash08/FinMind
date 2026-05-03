"""Comprehensive tests for multi-account management."""
import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app.models import Account, AccountType
from app.services.accounts import AccountService


# ── helpers ──────────────────────────────────────────────────


def _create_account(client, headers, name="Main Checking", account_type="checking", balance=1000.0):
    return client.post(
        "/accounts",
        json={
            "name": name,
            "account_type": account_type,
            "balance": balance,
        },
        headers=headers,
    )


# ── CRUD tests ───────────────────────────────────────────────


def test_create_account(client, auth_header):
    r = _create_account(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Main Checking"
    assert data["account_type"] == "checking"
    assert data["balance"] == 1000.0
    assert data["currency"] == "INR"
    assert data["is_active"] is True
    assert data["institution"] is None


def test_create_account_with_institution(client, auth_header):
    r = client.post(
        "/accounts",
        json={
            "name": "Chase Checking",
            "account_type": "checking",
            "institution": "Chase Bank",
            "balance": 5000,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["institution"] == "Chase Bank"


def test_create_account_all_types(client, auth_header):
    for atype in ["checking", "savings", "credit_card", "investment", "cash", "other"]:
        r = _create_account(client, auth_header, name=f"Test {atype}", account_type=atype)
        assert r.status_code == 201
        assert r.get_json()["account_type"] == atype


def test_list_accounts_empty(client, auth_header):
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_accounts_with_data(client, auth_header):
    _create_account(client, auth_header, "Account A", "checking", 500)
    _create_account(client, auth_header, "Account B", "savings", 1000)
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2
    names = {a["name"] for a in items}
    assert names == {"Account A", "Account B"}


def test_get_account(client, auth_header):
    r = _create_account(client, auth_header)
    aid = r.get_json()["id"]
    r = client.get(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == aid


def test_get_account_not_found(client, auth_header):
    r = client.get("/accounts/9999", headers=auth_header)
    assert r.status_code == 404


def test_update_account(client, auth_header):
    r = _create_account(client, auth_header, "Old Name", "checking", 500)
    aid = r.get_json()["id"]
    r = client.patch(
        f"/accounts/{aid}",
        json={"name": "New Name", "balance": 800, "institution": "New Bank"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "New Name"
    assert data["balance"] == 800.0
    assert data["institution"] == "New Bank"


def test_update_account_type(client, auth_header):
    r = _create_account(client, auth_header, "Convert", "checking", 100)
    aid = r.get_json()["id"]
    r = client.patch(f"/accounts/{aid}", json={"account_type": "savings"}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["account_type"] == "savings"


def test_update_account_not_found(client, auth_header):
    r = client.patch("/accounts/9999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404


def test_deactivate_account(client, auth_header):
    r = _create_account(client, auth_header)
    aid = r.get_json()["id"]
    r = client.patch(f"/accounts/{aid}", json={"is_active": False}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["is_active"] is False


def test_delete_account(client, auth_header):
    r = _create_account(client, auth_header)
    aid = r.get_json()["id"]
    r = client.delete(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"
    r = client.get(f"/accounts/{aid}", headers=auth_header)
    assert r.status_code == 404


def test_delete_account_not_found(client, auth_header):
    r = client.delete("/accounts/9999", headers=auth_header)
    assert r.status_code == 404


# ── Validation tests ─────────────────────────────────────────


def test_create_missing_name(client, auth_header):
    r = client.post("/accounts", json={"account_type": "checking"}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_empty_name(client, auth_header):
    r = client.post("/accounts", json={"name": "  ", "account_type": "checking"}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_missing_type(client, auth_header):
    r = client.post("/accounts", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]


def test_create_invalid_type(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "bitcoin"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "invalid account_type" in r.get_json()["error"]


def test_create_negative_balance(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "checking", "balance": -100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "negative" in r.get_json()["error"]


def test_create_invalid_balance(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "checking", "balance": "abc"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "valid number" in r.get_json()["error"]


def test_update_empty_name(client, auth_header):
    r = _create_account(client, auth_header)
    aid = r.get_json()["id"]
    r = client.patch(f"/accounts/{aid}", json={"name": ""}, headers=auth_header)
    assert r.status_code == 400
    assert "empty" in r.get_json()["error"]


def test_update_invalid_type(client, auth_header):
    r = _create_account(client, auth_header)
    aid = r.get_json()["id"]
    r = client.patch(f"/accounts/{aid}", json={"account_type": "crypto"}, headers=auth_header)
    assert r.status_code == 400
    assert "invalid account_type" in r.get_json()["error"]


def test_update_negative_balance(client, auth_header):
    r = _create_account(client, auth_header)
    aid = r.get_json()["id"]
    r = client.patch(f"/accounts/{aid}", json={"balance": -50}, headers=auth_header)
    assert r.status_code == 400
    assert "negative" in r.get_json()["error"]


# ── Summary tests ────────────────────────────────────────────


def test_summary_empty(client, auth_header):
    r = client.get("/accounts/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_accounts"] == 0
    assert data["total_balance"] == 0
    assert data["by_type"] == {}


def test_summary_with_accounts(client, auth_header):
    _create_account(client, auth_header, "Checking", "checking", 1000)
    _create_account(client, auth_header, "Savings", "savings", 5000)
    _create_account(client, auth_header, "Card", "credit_card", 200)

    r = client.get("/accounts/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_accounts"] == 3
    assert data["total_balance"] == 6200.0
    assert data["by_type"]["checking"]["count"] == 1
    assert data["by_type"]["checking"]["balance"] == 1000.0
    assert data["by_type"]["savings"]["count"] == 1
    assert data["by_type"]["savings"]["balance"] == 5000.0
    assert data["by_type"]["credit_card"]["count"] == 1
    assert data["by_type"]["credit_card"]["balance"] == 200.0


def test_summary_excludes_inactive(client, auth_header):
    r = _create_account(client, auth_header, "Active", "checking", 1000)
    aid = r.get_json()["id"]
    _create_account(client, auth_header, "Inactive", "savings", 2000)
    client.patch(f"/accounts/{aid}", json={"is_active": False}, headers=auth_header)

    r = client.get("/accounts/summary", headers=auth_header)
    data = r.get_json()
    assert data["total_accounts"] == 1
    assert data["total_balance"] == 2000.0


def test_summary_type_breakdown_multiple(client, auth_header):
    _create_account(client, auth_header, "Chk1", "checking", 100)
    _create_account(client, auth_header, "Chk2", "checking", 200)
    _create_account(client, auth_header, "Sav1", "savings", 500)

    r = client.get("/accounts/summary", headers=auth_header)
    data = r.get_json()
    assert data["by_type"]["checking"]["count"] == 2
    assert data["by_type"]["checking"]["balance"] == 300.0
    assert data["by_type"]["savings"]["count"] == 1
    assert data["by_type"]["savings"]["balance"] == 500.0


# ── Edge cases ───────────────────────────────────────────────


def test_zero_balance(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Empty", "account_type": "checking", "balance": 0},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["balance"] == 0.0


def test_custom_currency(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Euro Account", "account_type": "savings", "currency": "EUR", "balance": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_user_isolation(client, auth_header):
    """Users cannot see other users' accounts."""
    _create_account(client, auth_header, "My Account", "checking", 1000)

    # Register second user
    client.post("/auth/register", json={"email": "other@example.com", "password": "password123"})
    r = client.post("/auth/login", json={"email": "other@example.com", "password": "password123"})
    other_headers = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = client.get("/accounts", headers=other_headers)
    assert r.status_code == 200
    assert r.get_json() == []


def test_auth_required(client):
    """All accounts endpoints require authentication."""
    r = client.get("/accounts")
    assert r.status_code == 401
    r = client.post("/accounts", json={"name": "X", "account_type": "checking"})
    assert r.status_code == 401


# ── Service layer unit tests ─────────────────────────────────


def test_service_create_and_get(app_fixture):
    with app_fixture.app_context():
        from app.models import User
        u = User(email="svc@test.com", password_hash="x")
        db.session.add(u)
        db.session.flush()

        svc = AccountService()
        account, err = svc.create_account(u.id, {"name": "Test", "account_type": "checking", "balance": 500})
        assert err is None
        assert account.name == "Test"
        assert float(account.balance) == 500.0

        found = svc.get_account(u.id, account.id)
        assert found is not None
        assert found.id == account.id


def test_service_summary(app_fixture):
    with app_fixture.app_context():
        from app.models import User
        u = User(email="sum@test.com", password_hash="x")
        db.session.add(u)
        db.session.flush()

        svc = AccountService()
        svc.create_account(u.id, {"name": "A", "account_type": "checking", "balance": 100})
        svc.create_account(u.id, {"name": "B", "account_type": "savings", "balance": 200})
        svc.create_account(u.id, {"name": "C", "account_type": "checking", "balance": 300})

        summary = svc.get_summary(u.id)
        assert summary["total_accounts"] == 3
        assert summary["total_balance"] == 600.0
        assert summary["by_type"]["checking"]["count"] == 2
        assert summary["by_type"]["checking"]["balance"] == 400.0
        assert summary["by_type"]["savings"]["count"] == 1
        assert summary["by_type"]["savings"]["balance"] == 200.0
