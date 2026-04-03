"""Tests for Keyboard Navigation & Shortcuts (issue #106)."""
import pytest
from werkzeug.security import generate_password_hash
from app.services.keyboard_shortcuts import (
    get_all_shortcuts,
    get_shortcuts_by_category,
    get_user_shortcut_config,
    update_shortcut,
    reset_shortcut,
    reset_all_shortcuts,
    DEFAULT_SHORTCUTS,
    UserShortcutPreference,
)
from app.models import User
from app.extensions import db

try:
    import redis as _redis_lib
    _r = _redis_lib.Redis.from_url("redis://localhost:6379/15")
    _r.ping()
    _redis_available = True
except Exception:
    _redis_available = False

requires_redis = pytest.mark.skipif(
    not _redis_available, reason="Redis not available"
)


def _make_user(email="kb@test.com"):
    user = User(
        email=email,
        password_hash=generate_password_hash("pass"),
        preferred_currency="USD",
    )
    db.session.add(user)
    db.session.flush()
    return user


# -----------------------------------------------------------------------
# Unit tests (no DB)
# -----------------------------------------------------------------------

class TestDefaultShortcuts:
    def test_get_all_shortcuts(self):
        shortcuts = get_all_shortcuts()
        assert len(shortcuts) > 0
        for s in shortcuts:
            assert "action" in s
            assert "label" in s
            assert "default_key" in s
            assert "category" in s

    def test_shortcuts_by_category(self):
        by_cat = get_shortcuts_by_category()
        assert "navigation" in by_cat
        assert "actions" in by_cat
        assert "ui" in by_cat

    def test_navigation_shortcuts_present(self):
        shortcuts = get_all_shortcuts()
        actions = [s["action"] for s in shortcuts]
        assert "nav.dashboard" in actions
        assert "nav.expenses" in actions
        assert "nav.bills" in actions

    def test_action_shortcuts_present(self):
        shortcuts = get_all_shortcuts()
        actions = [s["action"] for s in shortcuts]
        assert "action.search" in actions
        assert "action.new_expense" in actions

    def test_ui_shortcuts_present(self):
        shortcuts = get_all_shortcuts()
        actions = [s["action"] for s in shortcuts]
        assert "ui.help" in actions
        assert "ui.close_modal" in actions
        assert "ui.next_item" in actions
        assert "ui.prev_item" in actions

    def test_at_least_15_shortcuts(self):
        shortcuts = get_all_shortcuts()
        assert len(shortcuts) >= 15

    def test_each_shortcut_has_description(self):
        for s in get_all_shortcuts():
            assert "description" in s
            assert len(s["description"]) > 0


# -----------------------------------------------------------------------
# Integration tests
# -----------------------------------------------------------------------

class TestUserShortcutConfig:
    def test_get_config_defaults_for_new_user(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("newkb@test.com")
            db.session.commit()
            config = get_user_shortcut_config(user.id)
            assert len(config) == len(DEFAULT_SHORTCUTS)
            for s in config:
                assert s["is_customized"] is False
                assert s["active_key"] == s["default_key"]

    def test_update_creates_preference(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("updatekb@test.com")
            db.session.commit()
            result = update_shortcut(user.id, "action.search", "ctrl+k")
            assert result is not None
            assert result["custom_key"] == "ctrl+k"
            assert result["is_customized"] is True

    def test_update_reflects_in_config(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("configkb@test.com")
            db.session.commit()
            update_shortcut(user.id, "nav.dashboard", "ctrl+1")
            config = get_user_shortcut_config(user.id)
            dash = next(s for s in config if s["action"] == "nav.dashboard")
            assert dash["custom_key"] == "ctrl+1"
            assert dash["active_key"] == "ctrl+1"
            assert dash["is_customized"] is True

    def test_update_unknown_action_returns_none(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("unknownkb@test.com")
            db.session.commit()
            result = update_shortcut(user.id, "nonexistent.action", "x")
            assert result is None

    def test_conflict_detection(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("conflictkb@test.com")
            db.session.commit()
            update_shortcut(user.id, "action.search", "ctrl+k")
            result = update_shortcut(user.id, "nav.dashboard", "ctrl+k")
            assert result is not None
            assert "error" in result

    def test_reset_removes_customization(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("resetkb@test.com")
            db.session.commit()
            update_shortcut(user.id, "nav.expenses", "ctrl+5")
            result = reset_shortcut(user.id, "nav.expenses")
            assert result is not None
            assert result["is_customized"] is False
            config = get_user_shortcut_config(user.id)
            exp = next(s for s in config if s["action"] == "nav.expenses")
            assert exp["is_customized"] is False

    def test_reset_all_clears_all(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("resetallkb@test.com")
            db.session.commit()
            update_shortcut(user.id, "nav.dashboard", "1")
            update_shortcut(user.id, "nav.bills", "2")
            count = reset_all_shortcuts(user.id)
            assert count == 2
            config = get_user_shortcut_config(user.id)
            customized = [s for s in config if s["is_customized"]]
            assert len(customized) == 0

    def test_disable_shortcut(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("disablekb@test.com")
            db.session.commit()
            update_shortcut(user.id, "action.import", "ctrl+i", enabled=False)
            config = get_user_shortcut_config(user.id)
            imp = next(s for s in config if s["action"] == "action.import")
            assert imp["enabled"] is False
            assert imp["active_key"] is None


# -----------------------------------------------------------------------
# API tests (require Redis)
# -----------------------------------------------------------------------

@requires_redis
class TestKeyboardShortcutsAPI:
    def test_list_shortcuts_public(self, client):
        resp = client.get("/keyboard-shortcuts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "shortcuts" in data
        assert data["count"] >= 15

    def test_list_shortcuts_by_category(self, client):
        resp = client.get("/keyboard-shortcuts?by_category=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "navigation" in data
        assert "actions" in data

    def test_get_user_shortcuts(self, client, auth_header):
        resp = client.get("/keyboard-shortcuts/user", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "shortcuts" in data

    def test_set_custom_shortcut(self, client, auth_header):
        resp = client.put("/keyboard-shortcuts/user/action.search",
                          json={"key": "ctrl+space"},
                          headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["custom_key"] == "ctrl+space"

    def test_set_unknown_action(self, client, auth_header):
        resp = client.put("/keyboard-shortcuts/user/fake.action",
                          json={"key": "x"},
                          headers=auth_header)
        assert resp.status_code == 404

    def test_reset_shortcut(self, client, auth_header):
        client.put("/keyboard-shortcuts/user/nav.dashboard",
                   json={"key": "ctrl+0"}, headers=auth_header)
        resp = client.delete("/keyboard-shortcuts/user/nav.dashboard", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_customized"] is False

    def test_reset_all(self, client, auth_header):
        resp = client.post("/keyboard-shortcuts/user/reset-all", headers=auth_header)
        assert resp.status_code == 200

    def test_list_shortcuts_requires_no_auth(self, client):
        resp = client.get("/keyboard-shortcuts")
        assert resp.status_code == 200