"""Tests for expense splitting & shared costs."""

import pytest
from app.services.expense_splitting import (
    create_group, get_groups, get_group, delete_group,
    add_expense, get_balances, calculate_settlements,
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
def group(app, user):
    with app.app_context():
        return create_group(user, "Trip", [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob"},
            {"name": "Charlie"},
        ])


class TestGroupCRUD:
    def test_create(self, app, user):
        with app.app_context():
            g = create_group(user, "Dinner", [{"name": "A"}, {"name": "B"}])
            assert g["name"] == "Dinner"
            assert len(g["members"]) == 2

    def test_create_too_few_members(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                create_group(user, "Solo", [{"name": "A"}])

    def test_list(self, app, user, group):
        with app.app_context():
            groups = get_groups(user)
            assert len(groups) == 1

    def test_get(self, app, user, group):
        with app.app_context():
            g = get_group(user, group["id"])
            assert g["name"] == "Trip"

    def test_delete(self, app, user, group):
        with app.app_context():
            assert delete_group(user, group["id"]) is True
            assert get_group(user, group["id"]) is None


class TestExpenseSplitting:
    def test_equal_split(self, app, user, group):
        with app.app_context():
            members = group["members"]
            exp = add_expense(user, group["id"], "Dinner", 90, members[0]["id"])
            assert exp["amount"] == 90
            assert len(exp["shares"]) == 3
            assert all(s["amount"] == 30 for s in exp["shares"])

    def test_exact_split(self, app, user, group):
        with app.app_context():
            members = group["members"]
            shares = [
                {"member_id": members[0]["id"], "amount": 50},
                {"member_id": members[1]["id"], "amount": 30},
                {"member_id": members[2]["id"], "amount": 20},
            ]
            exp = add_expense(user, group["id"], "Hotel", 100, members[0]["id"],
                              split_type="exact", shares=shares)
            assert exp["shares"][0]["amount"] == 50

    def test_percentage_split(self, app, user, group):
        with app.app_context():
            members = group["members"]
            shares = [
                {"member_id": members[0]["id"], "percentage": 50},
                {"member_id": members[1]["id"], "percentage": 30},
                {"member_id": members[2]["id"], "percentage": 20},
            ]
            exp = add_expense(user, group["id"], "Car", 200, members[1]["id"],
                              split_type="percentage", shares=shares)
            assert exp["shares"][0]["amount"] == 100

    def test_invalid_amount(self, app, user, group):
        with app.app_context():
            with pytest.raises(ValueError):
                add_expense(user, group["id"], "Bad", -10, group["members"][0]["id"])


class TestBalances:
    def test_equal_split_balances(self, app, user, group):
        with app.app_context():
            members = group["members"]
            add_expense(user, group["id"], "Dinner", 90, members[0]["id"])
            bal = get_balances(user, group["id"])
            balances = {b["name"]: b["balance"] for b in bal["balances"]}
            assert balances["Alice"] == 60  # paid 90, owes 30
            assert balances["Bob"] == -30
            assert balances["Charlie"] == -30

    def test_multiple_expenses(self, app, user, group):
        with app.app_context():
            members = group["members"]
            add_expense(user, group["id"], "Dinner", 90, members[0]["id"])
            add_expense(user, group["id"], "Taxi", 30, members[1]["id"])
            bal = get_balances(user, group["id"])
            total = sum(b["balance"] for b in bal["balances"])
            assert abs(total) < 0.01  # balances sum to zero


class TestSettlements:
    def test_simple(self, app, user, group):
        with app.app_context():
            members = group["members"]
            add_expense(user, group["id"], "Dinner", 90, members[0]["id"])
            settlements = calculate_settlements(user, group["id"])
            assert len(settlements) > 0
            for s in settlements:
                assert s["amount"] > 0
                assert "from_name" in s
                assert "to_name" in s

    def test_already_settled(self, app, user, group):
        with app.app_context():
            settlements = calculate_settlements(user, group["id"])
            assert len(settlements) == 0


class TestAPI:
    def test_create_group(self, app, user, token):
        client = app.test_client()
        resp = client.post("/splitting/groups",
                           json={"name": "Trip", "members": [{"name": "A"}, {"name": "B"}]},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_list_groups(self, app, user, token, group):
        client = app.test_client()
        resp = client.get("/splitting/groups", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_add_expense(self, app, user, token, group):
        client = app.test_client()
        resp = client.post(f"/splitting/groups/{group['id']}/expenses",
                           json={"description": "Food", "amount": 60, "paid_by_id": group["members"][0]["id"]},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_balances(self, app, user, token, group):
        client = app.test_client()
        resp = client.get(f"/splitting/groups/{group['id']}/balances",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_settlements(self, app, user, token, group):
        client = app.test_client()
        resp = client.get(f"/splitting/groups/{group['id']}/settlements",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
