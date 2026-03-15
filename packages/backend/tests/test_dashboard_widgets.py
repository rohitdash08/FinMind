"""Tests for customizable dashboard widgets."""

import pytest
from app.models import DashboardWidget
from app.extensions import db
from app.services.dashboard_widgets import (
    get_layout,
    initialize_layout,
    reset_layout,
    toggle_visibility,
    bulk_update_visibility,
    reorder_widgets,
    update_widget_config,
    get_widget,
    get_available_widgets,
    DEFAULT_WIDGETS,
)


# ── Service: get_layout ──────────────────────────────────────────


class TestGetLayout:
    def test_default_layout(self, app_fixture):
        with app_fixture.app_context():
            result = get_layout(1)
            assert len(result) == len(DEFAULT_WIDGETS)
            assert result[0]["widget_key"] == "spending_overview"

    def test_custom_layout(self, app_fixture):
        with app_fixture.app_context():
            initialize_layout(1)
            result = get_layout(1)
            assert len(result) == len(DEFAULT_WIDGETS)
            assert "id" in result[0]


# ── Service: initialize_layout ────────────────────────────────────


class TestInitializeLayout:
    def test_creates_widgets(self, app_fixture):
        with app_fixture.app_context():
            result = initialize_layout(1)
            assert len(result) == len(DEFAULT_WIDGETS)
            count = DashboardWidget.query.filter_by(user_id=1).count()
            assert count == len(DEFAULT_WIDGETS)

    def test_idempotent(self, app_fixture):
        with app_fixture.app_context():
            initialize_layout(1)
            initialize_layout(1)
            count = DashboardWidget.query.filter_by(user_id=1).count()
            assert count == len(DEFAULT_WIDGETS)


# ── Service: reset_layout ─────────────────────────────────────────


class TestResetLayout:
    def test_reset(self, app_fixture):
        with app_fixture.app_context():
            initialize_layout(1)
            # Modify a widget
            toggle_visibility(1, "spending_overview", False)
            # Reset
            result = reset_layout(1)
            assert all(w["visible"] for w in result)


# ── Service: visibility ───────────────────────────────────────────


class TestVisibility:
    def test_hide_widget(self, app_fixture):
        with app_fixture.app_context():
            result = toggle_visibility(1, "spending_overview", False)
            assert result["visible"] is False

    def test_show_widget(self, app_fixture):
        with app_fixture.app_context():
            toggle_visibility(1, "spending_overview", False)
            result = toggle_visibility(1, "spending_overview", True)
            assert result["visible"] is True

    def test_bulk_update(self, app_fixture):
        with app_fixture.app_context():
            result = bulk_update_visibility(1, {
                "spending_overview": False,
                "recent_transactions": False,
            })
            hidden = [w for w in result if not w["visible"]]
            assert len(hidden) == 2


# ── Service: reorder ─────────────────────────────────────────────


class TestReorder:
    def test_reorder_widgets(self, app_fixture):
        with app_fixture.app_context():
            new_order = ["upcoming_bills", "spending_overview", "recent_transactions"]
            result = reorder_widgets(1, new_order)
            # First 3 should be reordered
            keys = [w["widget_key"] for w in result[:3]]
            assert keys[0] == "upcoming_bills"
            assert keys[1] == "spending_overview"


# ── Service: config ───────────────────────────────────────────────


class TestWidgetConfig:
    def test_update_config(self, app_fixture):
        with app_fixture.app_context():
            result = update_widget_config(1, "spending_overview", {"period": "weekly"})
            assert result["config"]["period"] == "weekly"

    def test_get_widget(self, app_fixture):
        with app_fixture.app_context():
            result = get_widget(1, "spending_overview")
            assert result["widget_key"] == "spending_overview"

    def test_get_unknown_widget(self, app_fixture):
        with app_fixture.app_context():
            result = get_widget(1, "nonexistent_widget")
            assert "error" in result


# ── Service: available widgets ────────────────────────────────────


class TestAvailableWidgets:
    def test_list_available(self):
        result = get_available_widgets()
        assert len(result) == len(DEFAULT_WIDGETS)
        assert all("widget_key" in w for w in result)


# ── Routes ────────────────────────────────────────────────────────


class TestDashboardWidgetRoutes:
    def test_get_layout(self, client, auth_header):
        r = client.get("/widgets", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == len(DEFAULT_WIDGETS)

    def test_initialize(self, client, auth_header):
        r = client.post("/widgets/initialize", headers=auth_header)
        assert r.status_code == 201

    def test_reset(self, client, auth_header):
        client.post("/widgets/initialize", headers=auth_header)
        r = client.post("/widgets/reset", headers=auth_header)
        assert r.status_code == 200

    def test_toggle_visibility(self, client, auth_header):
        r = client.put("/widgets/spending_overview/visibility",
                       json={"visible": False},
                       headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["visible"] is False

    def test_toggle_visibility_missing_field(self, client, auth_header):
        r = client.put("/widgets/spending_overview/visibility",
                       json={},
                       headers=auth_header)
        assert r.status_code == 400

    def test_bulk_visibility(self, client, auth_header):
        r = client.put("/widgets/visibility",
                       json={"spending_overview": False},
                       headers=auth_header)
        assert r.status_code == 200

    def test_reorder(self, client, auth_header):
        r = client.put("/widgets/reorder",
                       json={"order": ["upcoming_bills", "spending_overview"]},
                       headers=auth_header)
        assert r.status_code == 200

    def test_reorder_missing_field(self, client, auth_header):
        r = client.put("/widgets/reorder",
                       json={},
                       headers=auth_header)
        assert r.status_code == 400

    def test_update_config(self, client, auth_header):
        r = client.put("/widgets/spending_overview/config",
                       json={"period": "weekly"},
                       headers=auth_header)
        assert r.status_code == 200

    def test_get_widget(self, client, auth_header):
        r = client.get("/widgets/spending_overview",
                       headers=auth_header)
        assert r.status_code == 200

    def test_available_widgets(self, client, auth_header):
        r = client.get("/widgets/available",
                       headers=auth_header)
        assert r.status_code == 200

    def test_unauthorized(self, client):
        r = client.get("/widgets")
        assert r.status_code == 401
