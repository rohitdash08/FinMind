"""Tests for multi-account financial overview."""

import pytest
from app.services.accounts import (
    AccountType,
    FinancialAccount,
    create_account,
    get_accounts,
    get_account,
    update_account,
    delete_account,
    overview,
)


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings

    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db

        db.create_all()
        yield app


@pytest.fixture
def user(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash

        u = User(email="test@example.com", password_hash=generate_password_hash("pass"))
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def token(app, user):
    with app.app_context():
        from flask_jwt_extended import create_access_token

        return create_access_token(identity=str(user))


class TestAccountService:
    def test_create_account(self, app, user):
        with app.app_context():
            acct = create_account(user, "Main Bank", AccountType.BANK, "USD", 1000)
            assert acct["name"] == "Main Bank"
            assert acct["account_type"] == "bank"
            assert acct["balance"] == 1000

    def test_create_invalid_type(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                create_account(user, "Bad", "invalid_type")

    def test_list_accounts(self, app, user):
        with app.app_context():
            create_account(user, "Bank A", AccountType.BANK)
            create_account(user, "Card B", AccountType.CREDIT_CARD)
            accts = get_accounts(user)
            assert len(accts) == 2

    def test_list_active_only(self, app, user):
        with app.app_context():
            create_account(user, "Active", AccountType.BANK)
            a2 = create_account(user, "Inactive", AccountType.CASH)
            update_account(user, a2["id"], is_active=False)
            active = get_accounts(user, active_only=True)
            all_accts = get_accounts(user, active_only=False)
            assert len(active) == 1
            assert len(all_accts) == 2

    def test_get_account(self, app, user):
        with app.app_context():
            created = create_account(user, "Test", AccountType.SAVINGS, balance=500)
            fetched = get_account(user, created["id"])
            assert fetched["name"] == "Test"
            assert fetched["balance"] == 500

    def test_get_nonexistent(self, app, user):
        with app.app_context():
            assert get_account(user, 9999) is None

    def test_update_account(self, app, user):
        with app.app_context():
            created = create_account(user, "Old Name", AccountType.BANK)
            updated = update_account(user, created["id"], name="New Name", balance=2000)
            assert updated["name"] == "New Name"
            assert updated["balance"] == 2000

    def test_update_nonexistent(self, app, user):
        with app.app_context():
            assert update_account(user, 9999, name="X") is None

    def test_delete_account(self, app, user):
        with app.app_context():
            created = create_account(user, "ToDelete", AccountType.CASH)
            assert delete_account(user, created["id"]) is True
            assert get_account(user, created["id"]) is None

    def test_delete_nonexistent(self, app, user):
        with app.app_context():
            assert delete_account(user, 9999) is False

    def test_overview(self, app, user):
        with app.app_context():
            create_account(user, "Bank", AccountType.BANK, "USD", 5000)
            create_account(user, "Card", AccountType.CREDIT_CARD, "USD", -500)
            create_account(user, "Cash", AccountType.CASH, "INR", 2000)
            result = overview(user)
            assert result["total_accounts"] == 3
            assert result["total_balance"] == 6500.0
            assert "bank" in result["by_type"]
            assert "USD" in result["by_currency"]
            assert "INR" in result["by_currency"]

    def test_overview_empty(self, app, user):
        with app.app_context():
            result = overview(user)
            assert result["total_accounts"] == 0
            assert result["total_balance"] == 0


class TestAccountAPI:
    def test_create_endpoint(self, app, user, token):
        client = app.test_client()
        resp = client.post(
            "/accounts/",
            json={"name": "My Bank", "account_type": "bank", "balance": 1000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["name"] == "My Bank"

    def test_create_missing_fields(self, app, user, token):
        client = app.test_client()
        resp = client.post(
            "/accounts/",
            json={"name": "No Type"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_list_endpoint(self, app, user, token):
        client = app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        client.post("/accounts/", json={"name": "A", "account_type": "bank"}, headers=h)
        client.post("/accounts/", json={"name": "B", "account_type": "cash"}, headers=h)
        resp = client.get("/accounts/", headers=h)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_overview_endpoint(self, app, user, token):
        client = app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        client.post("/accounts/", json={"name": "Bank", "account_type": "bank", "balance": 3000}, headers=h)
        resp = client.get("/accounts/overview", headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_balance"] == 3000

    def test_update_endpoint(self, app, user, token):
        client = app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/accounts/", json={"name": "Old", "account_type": "bank"}, headers=h)
        aid = r.get_json()["id"]
        resp = client.put(f"/accounts/{aid}", json={"name": "New"}, headers=h)
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "New"

    def test_delete_endpoint(self, app, user, token):
        client = app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/accounts/", json={"name": "Del", "account_type": "cash"}, headers=h)
        aid = r.get_json()["id"]
        resp = client.delete(f"/accounts/{aid}", headers=h)
        assert resp.status_code == 200

    def test_get_not_found(self, app, user, token):
        client = app.test_client()
        resp = client.get("/accounts/9999", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404
