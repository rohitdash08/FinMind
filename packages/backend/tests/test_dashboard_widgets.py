"""Tests for customizable dashboard widgets."""

import pytest
from app.services.dashboard_widgets import (
    get_catalog, get_widgets, add_widget, update_widget,
    delete_widget, reorder_widgets,
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


class TestCatalog:
    def test_has_entries(self, app):
        with app.app_context():
            catalog = get_catalog()
            assert len(catalog) >= 5
            assert all("type" in w and "title" in w for w in catalog)


class TestWidgets:
    def test_defaults_created(self, app, user):
        with app.app_context():
            widgets = get_widgets(user)
            assert len(widgets) == 5
            assert widgets[0]["widget_type"] == "spending_summary"

    def test_add(self, app, user):
        with app.app_context():
            get_widgets(user)  # init defaults
            w = add_widget(user, "alerts", title="My Alerts")
            assert w["widget_type"] == "alerts"
            assert w["title"] == "My Alerts"

    def test_add_invalid_type(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                add_widget(user, "nonexistent")

    def test_add_invalid_width(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                add_widget(user, "alerts", width="huge")

    def test_update(self, app, user):
        with app.app_context():
            widgets = get_widgets(user)
            updated = update_widget(user, widgets[0]["id"], title="New Title", visible=False)
            assert updated["title"] == "New Title"
            assert updated["visible"] is False

    def test_update_not_found(self, app, user):
        with app.app_context():
            assert update_widget(user, 9999, title="X") is None

    def test_delete(self, app, user):
        with app.app_context():
            widgets = get_widgets(user)
            assert delete_widget(user, widgets[0]["id"]) is True
            remaining = get_widgets(user)
            assert len(remaining) == 4

    def test_delete_not_found(self, app, user):
        with app.app_context():
            assert delete_widget(user, 9999) is False

    def test_reorder(self, app, user):
        with app.app_context():
            widgets = get_widgets(user)
            ids = [w["id"] for w in reversed(widgets)]
            reordered = reorder_widgets(user, ids)
            assert reordered[0]["id"] == ids[0]


class TestAPI:
    def test_catalog(self, app, user, token):
        client = app.test_client()
        resp = client.get("/widgets/catalog", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_list(self, app, user, token):
        client = app.test_client()
        resp = client.get("/widgets/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_create(self, app, user, token):
        client = app.test_client()
        resp = client.post("/widgets/", json={"widget_type": "alerts"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_update(self, app, user, token):
        client = app.test_client()
        resp = client.get("/widgets/", headers={"Authorization": f"Bearer {token}"})
        wid = resp.get_json()[0]["id"]
        resp = client.put(f"/widgets/{wid}", json={"title": "Updated"},
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_delete(self, app, user, token):
        client = app.test_client()
        resp = client.get("/widgets/", headers={"Authorization": f"Bearer {token}"})
        wid = resp.get_json()[0]["id"]
        resp = client.delete(f"/widgets/{wid}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_reorder(self, app, user, token):
        client = app.test_client()
        resp = client.get("/widgets/", headers={"Authorization": f"Bearer {token}"})
        ids = [w["id"] for w in resp.get_json()]
        resp = client.post("/widgets/reorder", json={"widget_ids": list(reversed(ids))},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
