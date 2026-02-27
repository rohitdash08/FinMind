"""Tests for event-driven financial activity system."""

import pytest
from app.services.event_system import (
    publish, get_events, subscribe, get_subscriptions,
    unsubscribe, get_event_types, register_handler, clear_handlers,
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
    clear_handlers()


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


class TestPublish:
    def test_basic(self, app, user):
        with app.app_context():
            e = publish(user, "expense.created", {"amount": 50})
            assert e["event_type"] == "expense.created"
            assert e["payload"]["amount"] == 50

    def test_invalid_type(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                publish(user, "invalid.type")

    def test_handler_called(self, app, user):
        with app.app_context():
            called = []
            register_handler("expense.created", lambda t, p, u: called.append(t))
            publish(user, "expense.created")
            assert len(called) == 1

    def test_wildcard_handler(self, app, user):
        with app.app_context():
            called = []
            register_handler("*", lambda t, p, u: called.append(t))
            publish(user, "expense.created")
            publish(user, "goal.completed")
            assert len(called) == 2


class TestGetEvents:
    def test_empty(self, app, user):
        with app.app_context():
            assert get_events(user) == []

    def test_with_data(self, app, user):
        with app.app_context():
            publish(user, "expense.created")
            publish(user, "budget.exceeded")
            events = get_events(user)
            assert len(events) == 2

    def test_filter_type(self, app, user):
        with app.app_context():
            publish(user, "expense.created")
            publish(user, "budget.exceeded")
            events = get_events(user, event_type="expense.created")
            assert len(events) == 1

    def test_limit(self, app, user):
        with app.app_context():
            for _ in range(5):
                publish(user, "expense.created")
            events = get_events(user, limit=3)
            assert len(events) == 3


class TestSubscriptions:
    def test_subscribe(self, app, user):
        with app.app_context():
            sub = subscribe(user, "expense.created", "https://example.com/hook")
            assert sub["event_type"] == "expense.created"
            assert sub["webhook_url"] == "https://example.com/hook"

    def test_subscribe_wildcard(self, app, user):
        with app.app_context():
            sub = subscribe(user, "*")
            assert sub["event_type"] == "*"

    def test_invalid_type(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                subscribe(user, "bad.type")

    def test_list(self, app, user):
        with app.app_context():
            subscribe(user, "expense.created")
            subscribe(user, "goal.completed")
            subs = get_subscriptions(user)
            assert len(subs) == 2

    def test_unsubscribe(self, app, user):
        with app.app_context():
            sub = subscribe(user, "expense.created")
            assert unsubscribe(user, sub["id"]) is True
            subs = get_subscriptions(user)
            assert len(subs) == 0

    def test_unsubscribe_not_found(self, app, user):
        with app.app_context():
            assert unsubscribe(user, 9999) is False


class TestEventTypes:
    def test_list(self, app):
        with app.app_context():
            types = get_event_types()
            assert "expense.created" in types
            assert "goal.completed" in types


class TestAPI:
    def test_types(self, app, user, token):
        client = app.test_client()
        resp = client.get("/events/types", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_publish(self, app, user, token):
        client = app.test_client()
        resp = client.post("/events/publish",
                           json={"event_type": "expense.created", "payload": {"amount": 10}},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_list_events(self, app, user, token):
        client = app.test_client()
        resp = client.get("/events/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_subscribe(self, app, user, token):
        client = app.test_client()
        resp = client.post("/events/subscriptions",
                           json={"event_type": "expense.created"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_list_subs(self, app, user, token):
        client = app.test_client()
        resp = client.get("/events/subscriptions", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_unsub(self, app, user, token):
        client = app.test_client()
        resp = client.post("/events/subscriptions",
                           json={"event_type": "expense.created"},
                           headers={"Authorization": f"Bearer {token}"})
        sub_id = resp.get_json()["id"]
        resp = client.delete(f"/events/subscriptions/{sub_id}",
                             headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
