"""Tests for weekly/monthly financial digest."""

import pytest
from datetime import date, timedelta
from app.services.financial_digest import generate_digest, get_digest_history


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
        food = Category(user_id=user, name="Food")
        transport = Category(user_id=user, name="Transport")
        shopping = Category(user_id=user, name="Shopping")
        db.session.add_all([food, transport, shopping])
        db.session.flush()
        today = date.today()
        for i in range(30):
            d = today - timedelta(days=i)
            db.session.add(Expense(user_id=user, category_id=food.id, amount=30, description="lunch", date=d))
            db.session.add(Expense(user_id=user, category_id=transport.id, amount=15, description="bus", date=d))
            if i % 3 == 0:
                db.session.add(Expense(user_id=user, category_id=shopping.id, amount=80, description="stuff", date=d))
        db.session.commit()
        return user


class TestDigest:
    def test_weekly_empty(self, app, user):
        with app.app_context():
            d = generate_digest(user, "weekly")
            assert d["period"] == "weekly"
            assert d["summary"]["total_spent"] == 0

    def test_monthly_empty(self, app, user):
        with app.app_context():
            d = generate_digest(user, "monthly")
            assert d["period"] == "monthly"

    def test_weekly_with_data(self, app, seed_expenses):
        with app.app_context():
            d = generate_digest(seed_expenses, "weekly")
            assert d["summary"]["total_spent"] > 0
            assert d["summary"]["transaction_count"] > 0
            assert d["summary"]["daily_average"] > 0
            assert d["summary"]["trend"] in ("up", "down", "stable")
            assert len(d["top_categories"]) > 0
            assert len(d["daily_breakdown"]) == 7
            assert len(d["highlights"]) > 0

    def test_monthly_with_data(self, app, seed_expenses):
        with app.app_context():
            d = generate_digest(seed_expenses, "monthly")
            assert d["summary"]["total_spent"] > 0
            assert d["period"] == "monthly"

    def test_top_categories_sorted(self, app, seed_expenses):
        with app.app_context():
            d = generate_digest(seed_expenses, "weekly")
            cats = d["top_categories"]
            for i in range(len(cats) - 1):
                assert cats[i]["total"] >= cats[i + 1]["total"]

    def test_category_percentages(self, app, seed_expenses):
        with app.app_context():
            d = generate_digest(seed_expenses, "weekly")
            cats = d["top_categories"]
            total_pct = sum(c["percentage"] for c in cats)
            assert abs(total_pct - 100) < 1

    def test_change_pct(self, app, seed_expenses):
        with app.app_context():
            d = generate_digest(seed_expenses, "weekly")
            assert "change_pct" in d["summary"]
            assert "previous_total" in d["summary"]


class TestHistory:
    def test_empty(self, app, user):
        with app.app_context():
            h = get_digest_history(user, 5)
            assert len(h) == 5
            assert all(w["total"] == 0 for w in h)

    def test_with_data(self, app, seed_expenses):
        with app.app_context():
            h = get_digest_history(seed_expenses, 4)
            assert len(h) == 4
            assert any(w["total"] > 0 for w in h)

    def test_custom_limit(self, app, user):
        with app.app_context():
            h = get_digest_history(user, 2)
            assert len(h) == 2


class TestAPI:
    def test_weekly(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get("/digest/?period=weekly", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["period"] == "weekly"

    def test_monthly(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get("/digest/?period=monthly", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_invalid_period(self, app, user, token):
        client = app.test_client()
        resp = client.get("/digest/?period=yearly", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    def test_default_weekly(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get("/digest/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["period"] == "weekly"

    def test_history(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get("/digest/history?limit=3", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.get_json()) == 3
