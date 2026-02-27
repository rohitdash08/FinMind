"""Tests for offline-first sync."""

import pytest
from datetime import datetime
from app.services.offline_sync import (
    queue_change, get_pending, sync_batch, get_changes_since,
    get_conflicts, resolve_conflict, get_sync_state, ENTITY_TYPES,
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


class TestQueueChange:
    def test_basic(self, app, user):
        with app.app_context():
            r = queue_change(user, "expense", "create", {"amount": 50}, datetime.utcnow())
            assert r["entity_type"] == "expense"
            assert r["action"] == "create"
            assert r["status"] == "pending"

    def test_invalid_entity(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                queue_change(user, "invalid", "create", {}, datetime.utcnow())

    def test_invalid_action(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                queue_change(user, "expense", "bad", {}, datetime.utcnow())


class TestPending:
    def test_empty(self, app, user):
        with app.app_context():
            assert get_pending(user) == []

    def test_with_data(self, app, user):
        with app.app_context():
            queue_change(user, "expense", "create", {}, datetime.utcnow())
            queue_change(user, "bill", "update", {}, datetime.utcnow())
            assert len(get_pending(user)) == 2


class TestSyncBatch:
    def test_basic(self, app, user):
        with app.app_context():
            changes = [
                {"entity_type": "expense", "action": "create",
                 "payload": {"amount": 10}, "client_timestamp": datetime.utcnow().isoformat()},
                {"entity_type": "category", "action": "update",
                 "payload": {"name": "Food"}, "client_timestamp": datetime.utcnow().isoformat()},
            ]
            result = sync_batch(user, changes)
            assert result["synced"] == 2
            assert result["total"] == 2
            assert result["sync_token"] is not None

    def test_empty(self, app, user):
        with app.app_context():
            result = sync_batch(user, [])
            assert result["synced"] == 0


class TestChangesSince:
    def test_all(self, app, user):
        with app.app_context():
            sync_batch(user, [
                {"entity_type": "expense", "action": "create",
                 "payload": , "client_timestamp": datetime.utcnow().isoformat()},
            ])
            changes = get_changes_since(user)
            assert len(changes) == 1

    def test_since(self, app, user):
        with app.app_context():
            before = datetime.utcnow()
            sync_batch(user, [
                {"entity_type": "expense", "action": "create",
                 "payload": {}, "client_timestamp": datetime.utcnow().isoformat()},
            ])
            changes = get_changes_since(user, before)
            assert len(changes) >= 1


class TestConflicts:
    def test_empty(self, app, user):
        with app.app_context():
            assert get_conflicts(user) == []

    def test_resolve_not_found(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                resolve_conflict(user, 9999, "accept")

    def test_invalid_resolution(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                resolve_conflict(user, 1, "maybe")


class TestSyncState:
    def test_initial(self, app, user):
        with app.app_context():
            s = get_sync_state(user)
            assert s["version"] == 0
            assert s["last_sync"] is None

    def test_after_sync(self, app, user):
        with app.app_context():
            sync_batch(user, [
                {"entity_type": "expense", "action": "create",
                 "payload": {}, "client_timestamp": datetime.utcnow().isoformat()},
            ])
            s = get_sync_state(user)
            assert s["version"] == 1
            assert s["last_sync"] is not None


class TestAPI:
    def test_state(self, app, user, token):
        client = app.test_client()
        resp = client.get("/sync/state", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_pending(self, app, user, token):
        client = app.test_client()
        resp = client.get("/sync/pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_push(self, app, user, token):
        client = app.test_client()
        resp = client.post("/sync/push", json={"changes": [
            {"entity_type": "expense", "action": "create",
             "payload": {"amount": 5}, "client_timestamp": datetime.utcnow().isoformat()},
        ]}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["synced"] == 1

    def test_pull(self, app, user, token):
        client = app.test_client()
        resp = client.get("/sync/pull", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_conflicts(self, app, user, token):
        client = app.test_client()
        resp = client.get("/sync/conflicts", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
