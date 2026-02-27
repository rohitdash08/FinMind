"""Tests for smart payee & merchant alias management."""

import pytest
from app.services.merchant_alias import (
    MerchantAlias, set_alias, get_aliases, delete_alias,
    resolve_name, suggest_merges, bulk_set_aliases, merchant_summary,
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


@pytest.fixture
def seed_expenses(app, user):
    with app.app_context():
        from app.extensions import db
        from app.models import Category, Expense
        from datetime import date
        cat = Category(user_id=user, name="Food")
        db.session.add(cat)
        db.session.flush()
        for desc in ["STARBUCKS #1234", "STARBUCKS #5678", "Starbucks Coffee", "MCDONALDS", "McDonalds #99"]:
            db.session.add(Expense(user_id=user, category_id=cat.id, amount=10, description=desc, date=date.today()))
        db.session.commit()
        return user


class TestAliasService:
    def test_set_alias(self, app, user):
        with app.app_context():
            a = set_alias(user, "STARBUCKS #1234", "Starbucks")
            assert a["raw_name"] == "STARBUCKS #1234"
            assert a["display_name"] == "Starbucks"

    def test_update_alias(self, app, user):
        with app.app_context():
            set_alias(user, "SBUX", "Starbucks")
            updated = set_alias(user, "SBUX", "Starbucks Coffee")
            assert updated["display_name"] == "Starbucks Coffee"

    def test_empty_raises(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                set_alias(user, "", "Name")

    def test_get_aliases(self, app, user):
        with app.app_context():
            set_alias(user, "A", "Alpha")
            set_alias(user, "B", "Beta")
            aliases = get_aliases(user)
            assert len(aliases) == 2

    def test_delete_alias(self, app, user):
        with app.app_context():
            a = set_alias(user, "DEL", "Delete Me")
            assert delete_alias(user, a["id"]) is True
            assert len(get_aliases(user)) == 0

    def test_delete_nonexistent(self, app, user):
        with app.app_context():
            assert delete_alias(user, 9999) is False

    def test_resolve_with_alias(self, app, user):
        with app.app_context():
            set_alias(user, "SBUX #123", "Starbucks")
            assert resolve_name(user, "SBUX #123") == "Starbucks"

    def test_resolve_without_alias(self, app, user):
        with app.app_context():
            assert resolve_name(user, "Unknown Store") == "Unknown Store"

    def test_bulk_set(self, app, user):
        with app.app_context():
            results = bulk_set_aliases(user, [
                {"raw_name": "A", "display_name": "Alpha"},
                {"raw_name": "B", "display_name": "Beta"},
            ])
            assert len(results) == 2

    def test_suggest_merges(self, app, seed_expenses):
        with app.app_context():
            suggestions = suggest_merges(seed_expenses, threshold=0.5)
            assert isinstance(suggestions, list)
            # Should find STARBUCKS variants as similar
            starbucks = [s for s in suggestions if any("STARBUCKS" in n or "Starbucks" in n for n in s["names"])]
            assert len(starbucks) > 0

    def test_merchant_summary(self, app, seed_expenses):
        with app.app_context():
            result = merchant_summary(seed_expenses)
            assert result["total_merchants"] == 5
            assert result["total_aliases"] == 0

    def test_summary_with_aliases(self, app, seed_expenses):
        with app.app_context():
            set_alias(seed_expenses, "STARBUCKS #1234", "Starbucks")
            set_alias(seed_expenses, "STARBUCKS #5678", "Starbucks")
            result = merchant_summary(seed_expenses)
            starbucks = [m for m in result["merchants"] if m["name"] == "Starbucks"]
            assert len(starbucks) == 1
            assert starbucks[0]["transaction_count"] == 2


class TestMerchantAPI:
    def test_create_alias(self, app, user, token):
        client = app.test_client()
        resp = client.post(
            "/merchants/aliases",
            json={"raw_name": "SBUX", "display_name": "Starbucks"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    def test_create_missing_fields(self, app, user, token):
        client = app.test_client()
        resp = client.post(
            "/merchants/aliases",
            json={"raw_name": "SBUX"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_list_aliases(self, app, user, token):
        client = app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        client.post("/merchants/aliases", json={"raw_name": "A", "display_name": "B"}, headers=h)
        resp = client.get("/merchants/aliases", headers=h)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_suggest_merges_endpoint(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get(
            "/merchants/suggest-merges",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_summary_endpoint(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get(
            "/merchants/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "total_merchants" in resp.get_json()

    def test_bulk_endpoint(self, app, user, token):
        client = app.test_client()
        resp = client.post(
            "/merchants/aliases/bulk",
            json={"aliases": [{"raw_name": "X", "display_name": "Y"}]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
