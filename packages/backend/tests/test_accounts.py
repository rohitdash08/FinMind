"""Tests for /accounts endpoints (issue #132).

Covers:
- Auth gates (401 without JWT)
- Create / list / get / update / delete
- Overview aggregation (assets vs liabilities, net_worth)
- Default account logic (first account auto-default; explicit is_default clears old)
- Validation errors (missing name, bad account_type, non-numeric balance)
- Cross-user isolation (user A cannot read/modify user B's accounts)
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DISABLE_SCHEDULER", "true")

# ---------------------------------------------------------------------------
# Patch Redis before app import
# ---------------------------------------------------------------------------
import app.extensions as _ext  # noqa: E402

_rc = _ext.redis_client
_rc.ping = lambda: True
_rc.get = lambda *a, **kw: None
_rc.set = lambda *a, **kw: True
_rc.setex = lambda *a, **kw: True
_rc.delete = lambda *a, **kw: 0
_rc.scan = lambda cursor=0, **kw: (0, [])
_rc.keys = lambda *a, **kw: []
_rc.expire = lambda *a, **kw: 1

from app import create_app  # noqa: E402
from app.config import Settings  # noqa: E402
from app.extensions import db as _db  # noqa: E402


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    jwt_secret: str = "test-secret-key-32chars-padding!!"
    jwt_access_minutes: int = 60


@pytest.fixture(scope="module")
def app():
    flask_app = create_app(TestSettings())
    flask_app.config["TESTING"] = True
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, email: str, password: str = "Pass1234!") -> str:
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return r.get_json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------

class TestAuthGates:
    def test_list_requires_auth(self, client):
        r = client.get("/accounts")
        assert r.status_code == 401

    def test_create_requires_auth(self, client):
        r = client.post("/accounts", json={"name": "Wallet"})
        assert r.status_code == 401

    def test_overview_requires_auth(self, client):
        r = client.get("/accounts/overview")
        assert r.status_code == 401

    def test_get_requires_auth(self, client):
        r = client.get("/accounts/1")
        assert r.status_code == 401

    def test_patch_requires_auth(self, client):
        r = client.patch("/accounts/1", json={"name": "X"})
        assert r.status_code == 401

    def test_delete_requires_auth(self, client):
        r = client.delete("/accounts/1")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreateAccount:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.token = _register_and_login(client, "create_acc@test.com")
        self.h = _auth(self.token)

    def test_create_minimal(self, client):
        r = client.post("/accounts", json={"name": "Main Wallet"}, headers=self.h)
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Main Wallet"
        assert data["account_type"] == "CHECKING"
        assert data["balance"] == 0.0
        assert data["is_default"] is True  # first account → auto default
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_full_fields(self, client):
        r = client.post("/accounts", json={
            "name": "HDFC Savings",
            "account_type": "savings",  # lowercase should be normalised
            "balance": "15000.50",
            "currency": "INR",
            "institution": "HDFC Bank",
            "notes": "Primary savings",
        }, headers=self.h)
        assert r.status_code == 201
        d = r.get_json()
        assert d["account_type"] == "SAVINGS"
        assert d["balance"] == pytest.approx(15000.50)
        assert d["institution"] == "HDFC Bank"
        assert d["notes"] == "Primary savings"

    def test_create_missing_name_400(self, client):
        r = client.post("/accounts", json={}, headers=self.h)
        assert r.status_code == 400
        assert "name" in r.get_json()["error"]

    def test_create_bad_type_400(self, client):
        r = client.post("/accounts", json={"name": "X", "account_type": "DEBIT"}, headers=self.h)
        assert r.status_code == 400
        assert "account_type" in r.get_json()["error"]

    def test_create_bad_balance_400(self, client):
        r = client.post("/accounts", json={"name": "X", "balance": "oops"}, headers=self.h)
        assert r.status_code == 400
        assert "balance" in r.get_json()["error"]

    def test_second_account_not_default(self, client):
        client.post("/accounts", json={"name": "First"}, headers=self.h)
        r = client.post("/accounts", json={"name": "Second"}, headers=self.h)
        assert r.status_code == 201
        assert r.get_json()["is_default"] is False

    def test_explicit_is_default_clears_old(self, client):
        r1 = client.post("/accounts", json={"name": "Alpha"}, headers=self.h)
        r2 = client.post("/accounts", json={"name": "Beta", "is_default": True}, headers=self.h)
        assert r2.get_json()["is_default"] is True
        # Alpha should no longer be default
        alpha_id = r1.get_json()["id"]
        r_alpha = client.get(f"/accounts/{alpha_id}", headers=self.h)
        assert r_alpha.get_json()["is_default"] is False


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class TestListAccounts:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.token = _register_and_login(client, "list_acc@test.com")
        self.h = _auth(self.token)

    def test_empty_list(self, client):
        r = client.get("/accounts", headers=self.h)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_returns_created_accounts(self, client):
        client.post("/accounts", json={"name": "A"}, headers=self.h)
        client.post("/accounts", json={"name": "B"}, headers=self.h)
        r = client.get("/accounts", headers=self.h)
        names = [a["name"] for a in r.get_json()]
        assert "A" in names
        assert "B" in names

    def test_default_account_first(self, client):
        token2 = _register_and_login(client, "list_order@test.com")
        h2 = _auth(token2)
        client.post("/accounts", json={"name": "Non-default"}, headers=h2)
        r2 = client.post("/accounts", json={"name": "MakeDefault", "is_default": True}, headers=h2)
        assert r2.get_json()["is_default"] is True
        listing = client.get("/accounts", headers=h2).get_json()
        assert listing[0]["name"] == "MakeDefault"


# ---------------------------------------------------------------------------
# Get single
# ---------------------------------------------------------------------------

class TestGetAccount:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.token = _register_and_login(client, "get_acc@test.com")
        self.h = _auth(self.token)
        r = client.post("/accounts", json={"name": "My Account"}, headers=self.h)
        self.acc_id = r.get_json()["id"]

    def test_get_existing(self, client):
        r = client.get(f"/accounts/{self.acc_id}", headers=self.h)
        assert r.status_code == 200
        assert r.get_json()["id"] == self.acc_id

    def test_get_missing_404(self, client):
        r = client.get("/accounts/999999", headers=self.h)
        assert r.status_code == 404

    def test_get_other_user_404(self, client):
        other = _register_and_login(client, "other_get@test.com")
        r = client.get(f"/accounts/{self.acc_id}", headers=_auth(other))
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class TestUpdateAccount:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.token = _register_and_login(client, "update_acc@test.com")
        self.h = _auth(self.token)
        r = client.post("/accounts", json={"name": "Old Name", "balance": 100}, headers=self.h)
        self.acc_id = r.get_json()["id"]

    def test_update_name(self, client):
        r = client.patch(f"/accounts/{self.acc_id}", json={"name": "New Name"}, headers=self.h)
        assert r.status_code == 200
        assert r.get_json()["name"] == "New Name"

    def test_update_balance(self, client):
        r = client.patch(f"/accounts/{self.acc_id}", json={"balance": 500}, headers=self.h)
        assert r.status_code == 200
        assert r.get_json()["balance"] == pytest.approx(500.0)

    def test_update_type(self, client):
        r = client.patch(f"/accounts/{self.acc_id}", json={"account_type": "SAVINGS"}, headers=self.h)
        assert r.status_code == 200
        assert r.get_json()["account_type"] == "SAVINGS"

    def test_update_bad_type_400(self, client):
        r = client.patch(f"/accounts/{self.acc_id}", json={"account_type": "INVALID"}, headers=self.h)
        assert r.status_code == 400

    def test_update_empty_name_400(self, client):
        r = client.patch(f"/accounts/{self.acc_id}", json={"name": "  "}, headers=self.h)
        assert r.status_code == 400

    def test_update_bad_balance_400(self, client):
        r = client.patch(f"/accounts/{self.acc_id}", json={"balance": "abc"}, headers=self.h)
        assert r.status_code == 400

    def test_update_missing_404(self, client):
        r = client.patch("/accounts/999999", json={"name": "X"}, headers=self.h)
        assert r.status_code == 404

    def test_update_other_user_404(self, client):
        other = _register_and_login(client, "other_upd@test.com")
        r = client.patch(f"/accounts/{self.acc_id}", json={"name": "X"}, headers=_auth(other))
        assert r.status_code == 404

    def test_set_default_via_patch(self, client):
        r2 = client.post("/accounts", json={"name": "Second"}, headers=self.h)
        id2 = r2.get_json()["id"]
        r = client.patch(f"/accounts/{id2}", json={"is_default": True}, headers=self.h)
        assert r.status_code == 200
        assert r.get_json()["is_default"] is True
        # Original should no longer be default
        r_orig = client.get(f"/accounts/{self.acc_id}", headers=self.h)
        assert r_orig.get_json()["is_default"] is False


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDeleteAccount:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.token = _register_and_login(client, "del_acc@test.com")
        self.h = _auth(self.token)
        r = client.post("/accounts", json={"name": "To Delete"}, headers=self.h)
        self.acc_id = r.get_json()["id"]

    def test_delete_existing(self, client):
        r = client.delete(f"/accounts/{self.acc_id}", headers=self.h)
        assert r.status_code == 204
        assert r.data == b""

    def test_delete_missing_404(self, client):
        r = client.delete("/accounts/999999", headers=self.h)
        assert r.status_code == 404

    def test_delete_other_user_404(self, client):
        token2 = _register_and_login(client, "del_other@test.com")
        r = client.post("/accounts", json={"name": "Mine"}, headers=self.h)
        id_ = r.get_json()["id"]
        r2 = client.delete(f"/accounts/{id_}", headers=_auth(token2))
        assert r2.status_code == 404

    def test_deleted_account_no_longer_visible(self, client):
        token = _register_and_login(client, "del_visible@test.com")
        h = _auth(token)
        r = client.post("/accounts", json={"name": "Gone"}, headers=h)
        aid = r.get_json()["id"]
        client.delete(f"/accounts/{aid}", headers=h)
        r2 = client.get(f"/accounts/{aid}", headers=h)
        assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

class TestOverview:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.token = _register_and_login(client, "overview_acc@test.com")
        self.h = _auth(self.token)

    def test_overview_empty(self, client):
        r = client.get("/accounts/overview", headers=self.h)
        assert r.status_code == 200
        d = r.get_json()
        assert d["account_count"] == 0
        assert d["total_assets"] == 0.0
        assert d["total_liabilities"] == 0.0
        assert d["net_worth"] == 0.0
        assert d["by_type"] == {}
        assert d["accounts"] == []

    def test_overview_assets_only(self, client):
        client.post("/accounts", json={"name": "Checking", "account_type": "CHECKING", "balance": 1000}, headers=self.h)
        client.post("/accounts", json={"name": "Savings", "account_type": "SAVINGS", "balance": 2000}, headers=self.h)
        r = client.get("/accounts/overview", headers=self.h)
        d = r.get_json()
        assert d["total_assets"] == pytest.approx(3000.0)
        assert d["total_liabilities"] == pytest.approx(0.0)
        assert d["net_worth"] == pytest.approx(3000.0)
        assert d["account_count"] == 2

    def test_overview_credit_as_liability(self, client):
        token = _register_and_login(client, "ov_credit@test.com")
        h = _auth(token)
        client.post("/accounts", json={"name": "Bank", "account_type": "CHECKING", "balance": 5000}, headers=h)
        client.post("/accounts", json={"name": "Card", "account_type": "CREDIT", "balance": 1500}, headers=h)
        r = client.get("/accounts/overview", headers=h)
        d = r.get_json()
        assert d["total_assets"] == pytest.approx(5000.0)
        assert d["total_liabilities"] == pytest.approx(1500.0)
        assert d["net_worth"] == pytest.approx(3500.0)

    def test_overview_by_type(self, client):
        token = _register_and_login(client, "ov_bytype@test.com")
        h = _auth(token)
        client.post("/accounts", json={"name": "C", "account_type": "CHECKING", "balance": 100}, headers=h)
        client.post("/accounts", json={"name": "S", "account_type": "SAVINGS", "balance": 200}, headers=h)
        r = client.get("/accounts/overview", headers=h)
        bt = r.get_json()["by_type"]
        assert bt["CHECKING"] == pytest.approx(100.0)
        assert bt["SAVINGS"] == pytest.approx(200.0)

    def test_overview_accounts_list_present(self, client):
        token = _register_and_login(client, "ov_list@test.com")
        h = _auth(token)
        client.post("/accounts", json={"name": "One"}, headers=h)
        r = client.get("/accounts/overview", headers=h)
        d = r.get_json()
        assert len(d["accounts"]) == 1
        assert d["accounts"][0]["name"] == "One"

    def test_overview_isolated_per_user(self, client):
        """User A's accounts don't appear in user B's overview."""
        ta = _register_and_login(client, "ov_userA@test.com")
        tb = _register_and_login(client, "ov_userB@test.com")
        client.post("/accounts", json={"name": "A's acc", "balance": 9999}, headers=_auth(ta))
        r = client.get("/accounts/overview", headers=_auth(tb))
        d = r.get_json()
        assert d["account_count"] == 0
        assert d["net_worth"] == 0.0


# ---------------------------------------------------------------------------
# All account types accepted
# ---------------------------------------------------------------------------

class TestAccountTypes:
    VALID_TYPES = ["CHECKING", "SAVINGS", "CREDIT", "INVESTMENT", "CASH", "OTHER"]

    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.token = _register_and_login(client, "types_acc@test.com")
        self.h = _auth(self.token)

    @pytest.mark.parametrize("atype", VALID_TYPES)
    def test_valid_type(self, client, atype):
        r = client.post("/accounts", json={"name": f"Acc {atype}", "account_type": atype}, headers=self.h)
        assert r.status_code == 201
        assert r.get_json()["account_type"] == atype
