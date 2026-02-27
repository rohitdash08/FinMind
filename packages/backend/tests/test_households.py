"""Tests for household collaborative budgeting."""

import pytest
from app.services.households import (
    Household, HouseholdMember, HouseholdBudget,
    create_household, get_user_households, get_household,
    add_member, remove_member, set_budget, get_budget_summary, delete_household,
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
def users(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash

        u1 = User(email="owner@example.com", password_hash=generate_password_hash("pass"))
        u2 = User(email="member@example.com", password_hash=generate_password_hash("pass"))
        u3 = User(email="outsider@example.com", password_hash=generate_password_hash("pass"))
        db.session.add_all([u1, u2, u3])
        db.session.commit()
        return u1.id, u2.id, u3.id


@pytest.fixture
def token_for(app, users):
    def _make(uid):
        with app.app_context():
            from flask_jwt_extended import create_access_token
            return create_access_token(identity=str(uid))
    return _make


class TestHouseholdService:
    def test_create(self, app, users):
        owner, _, _ = users
        with app.app_context():
            h = create_household(owner, "My Home")
            assert h["name"] == "My Home"
            assert h["owner_id"] == owner
            assert len(h["members"]) == 1
            assert h["members"][0]["role"] == "owner"

    def test_list_households(self, app, users):
        owner, _, _ = users
        with app.app_context():
            create_household(owner, "Home 1")
            create_household(owner, "Home 2")
            hs = get_user_households(owner)
            assert len(hs) == 2

    def test_get_household(self, app, users):
        owner, _, _ = users
        with app.app_context():
            h = create_household(owner, "Test")
            fetched = get_household(owner, h["id"])
            assert fetched["name"] == "Test"

    def test_get_household_denied(self, app, users):
        owner, _, outsider = users
        with app.app_context():
            h = create_household(owner, "Private")
            assert get_household(outsider, h["id"]) is None

    def test_add_member(self, app, users):
        owner, member, _ = users
        with app.app_context():
            h = create_household(owner, "Shared")
            result = add_member(owner, h["id"], "member@example.com")
            assert len(result["members"]) == 2

    def test_add_member_not_owner(self, app, users):
        owner, member, _ = users
        with app.app_context():
            h = create_household(owner, "Shared")
            assert add_member(member, h["id"], "outsider@example.com") is None

    def test_add_nonexistent_user(self, app, users):
        owner, _, _ = users
        with app.app_context():
            h = create_household(owner, "Test")
            assert add_member(owner, h["id"], "nobody@example.com") is None

    def test_add_duplicate_member(self, app, users):
        owner, member, _ = users
        with app.app_context():
            h = create_household(owner, "Test")
            add_member(owner, h["id"], "member@example.com")
            result = add_member(owner, h["id"], "member@example.com")
            assert len(result["members"]) == 2  # no duplicate

    def test_remove_member(self, app, users):
        owner, member, _ = users
        with app.app_context():
            h = create_household(owner, "Test")
            add_member(owner, h["id"], "member@example.com")
            assert remove_member(owner, h["id"], member) is True
            updated = get_household(owner, h["id"])
            assert len(updated["members"]) == 1

    def test_remove_owner_fails(self, app, users):
        owner, _, _ = users
        with app.app_context():
            h = create_household(owner, "Test")
            assert remove_member(owner, h["id"], owner) is False

    def test_set_budget(self, app, users):
        owner, _, _ = users
        with app.app_context():
            h = create_household(owner, "Home")
            result = set_budget(owner, h["id"], "Food", 5000, "2026-02")
            assert result["total_budget"] == 5000
            assert len(result["categories"]) == 1

    def test_set_budget_invalid(self, app, users):
        owner, _, _ = users
        with app.app_context():
            h = create_household(owner, "Home")
            with pytest.raises(ValueError):
                set_budget(owner, h["id"], "Food", -100)

    def test_budget_summary_empty(self, app, users):
        owner, _, _ = users
        with app.app_context():
            h = create_household(owner, "Home")
            result = get_budget_summary(owner, h["id"], "2026-02")
            assert result["total_budget"] == 0
            assert result["total_spent"] == 0

    def test_delete_household(self, app, users):
        owner, _, _ = users
        with app.app_context():
            h = create_household(owner, "Del")
            assert delete_household(owner, h["id"]) is True
            assert get_household(owner, h["id"]) is None

    def test_delete_not_owner(self, app, users):
        owner, member, _ = users
        with app.app_context():
            h = create_household(owner, "Test")
            add_member(owner, h["id"], "member@example.com")
            assert delete_household(member, h["id"]) is False


class TestHouseholdAPI:
    def test_create_endpoint(self, app, users, token_for):
        owner, _, _ = users
        client = app.test_client()
        resp = client.post(
            "/households/",
            json={"name": "API Home"},
            headers={"Authorization": f"Bearer {token_for(owner)}"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["name"] == "API Home"

    def test_create_missing_name(self, app, users, token_for):
        owner, _, _ = users
        client = app.test_client()
        resp = client.post(
            "/households/",
            json={},
            headers={"Authorization": f"Bearer {token_for(owner)}"},
        )
        assert resp.status_code == 400

    def test_list_endpoint(self, app, users, token_for):
        owner, _, _ = users
        client = app.test_client()
        h = {"Authorization": f"Bearer {token_for(owner)}"}
        client.post("/households/", json={"name": "H1"}, headers=h)
        resp = client.get("/households/", headers=h)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_add_member_endpoint(self, app, users, token_for):
        owner, member, _ = users
        client = app.test_client()
        h = {"Authorization": f"Bearer {token_for(owner)}"}
        r = client.post("/households/", json={"name": "Shared"}, headers=h)
        hid = r.get_json()["id"]
        resp = client.post(f"/households/{hid}/members", json={"email": "member@example.com"}, headers=h)
        assert resp.status_code == 200
        assert len(resp.get_json()["members"]) == 2

    def test_set_budget_endpoint(self, app, users, token_for):
        owner, _, _ = users
        client = app.test_client()
        h = {"Authorization": f"Bearer {token_for(owner)}"}
        r = client.post("/households/", json={"name": "Budget"}, headers=h)
        hid = r.get_json()["id"]
        resp = client.post(
            f"/households/{hid}/budgets",
            json={"category_name": "Food", "monthly_limit": 3000},
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.get_json()["total_budget"] == 3000

    def test_delete_endpoint(self, app, users, token_for):
        owner, _, _ = users
        client = app.test_client()
        h = {"Authorization": f"Bearer {token_for(owner)}"}
        r = client.post("/households/", json={"name": "Del"}, headers=h)
        hid = r.get_json()["id"]
        resp = client.delete(f"/households/{hid}", headers=h)
        assert resp.status_code == 200
