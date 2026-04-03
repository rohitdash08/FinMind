"""Tests for customizable dashboard widgets (issue #103)."""
from __future__ import annotations

import pytest


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def auth_header(app_fixture):
    """Generate JWT directly, bypassing Redis-dependent login."""
    from flask_jwt_extended import create_access_token
    from app.models import User
    from app.extensions import db
    from werkzeug.security import generate_password_hash

    with app_fixture.app_context():
        hashed = generate_password_hash("password123")
        user = User(email="widgets_test@example.com", password_hash=hashed)
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))

    return {"Authorization": f"Bearer {token}"}


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestGetWidgets:
    """GET /dashboard/widgets tests."""

    def test_requires_auth(self, client):
        r = client.get("/dashboard/widgets")
        assert r.status_code == 401

    def test_returns_default_config(self, client, auth_header):
        r = client.get("/dashboard/widgets", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "widgets" in data
        assert isinstance(data["widgets"], list)
        assert len(data["widgets"]) > 0

    def test_default_config_has_required_fields(self, client, auth_header):
        r = client.get("/dashboard/widgets", headers=auth_header)
        widgets = r.get_json()["widgets"]
        for w in widgets:
            assert "id" in w
            assert "label" in w
            assert "visible" in w
            assert "order" in w

    def test_default_sorted_by_order(self, client, auth_header):
        r = client.get("/dashboard/widgets", headers=auth_header)
        widgets = r.get_json()["widgets"]
        orders = [w["order"] for w in widgets]
        assert orders == sorted(orders)

    def test_monthly_summary_visible_by_default(self, client, auth_header):
        r = client.get("/dashboard/widgets", headers=auth_header)
        widgets = r.get_json()["widgets"]
        monthly = next((w for w in widgets if w["id"] == "monthly_summary"), None)
        assert monthly is not None
        assert monthly["visible"] is True


class TestUpdateWidgets:
    """PATCH /dashboard/widgets tests."""

    def test_requires_auth(self, client):
        r = client.patch("/dashboard/widgets", json={"updates": []})
        assert r.status_code == 401

    def test_hide_widget(self, client, auth_header):
        r = client.patch("/dashboard/widgets", json={
            "updates": [{"id": "monthly_summary", "visible": False}]
        }, headers=auth_header)
        assert r.status_code == 200
        widgets = r.get_json()["widgets"]
        monthly = next(w for w in widgets if w["id"] == "monthly_summary")
        assert monthly["visible"] is False

    def test_reorder_widget(self, client, auth_header):
        r = client.patch("/dashboard/widgets", json={
            "updates": [{"id": "upcoming_bills", "order": 0}]
        }, headers=auth_header)
        assert r.status_code == 200
        widgets = r.get_json()["widgets"]
        bills = next(w for w in widgets if w["id"] == "upcoming_bills")
        assert bills["order"] == 0

    def test_update_multiple_widgets(self, client, auth_header):
        r = client.patch("/dashboard/widgets", json={
            "updates": [
                {"id": "expense_chart", "visible": False},
                {"id": "savings_goals", "visible": True, "order": 1},
            ]
        }, headers=auth_header)
        assert r.status_code == 200
        widgets = r.get_json()["widgets"]
        chart = next(w for w in widgets if w["id"] == "expense_chart")
        savings = next(w for w in widgets if w["id"] == "savings_goals")
        assert chart["visible"] is False
        assert savings["visible"] is True
        assert savings["order"] == 1

    def test_ignores_unknown_widget_id(self, client, auth_header):
        r = client.patch("/dashboard/widgets", json={
            "updates": [{"id": "nonexistent_widget", "visible": False}]
        }, headers=auth_header)
        # Should succeed, just ignore unknown IDs
        assert r.status_code == 200

    def test_invalid_updates_not_list(self, client, auth_header):
        r = client.patch("/dashboard/widgets", json={
            "updates": "not_a_list"
        }, headers=auth_header)
        assert r.status_code == 400

    def test_update_missing_id(self, client, auth_header):
        r = client.patch("/dashboard/widgets", json={
            "updates": [{"visible": False}]
        }, headers=auth_header)
        assert r.status_code == 400

    def test_preferences_persist(self, client, auth_header):
        """Changes should be persisted across requests."""
        client.patch("/dashboard/widgets", json={
            "updates": [{"id": "cash_flow", "visible": True, "order": 0}]
        }, headers=auth_header)

        r = client.get("/dashboard/widgets", headers=auth_header)
        widgets = r.get_json()["widgets"]
        cash_flow = next(w for w in widgets if w["id"] == "cash_flow")
        assert cash_flow["visible"] is True
        assert cash_flow["order"] == 0


class TestResetWidgets:
    """POST /dashboard/widgets/reset tests."""

    def test_requires_auth(self, client):
        r = client.post("/dashboard/widgets/reset")
        assert r.status_code == 401

    def test_reset_returns_defaults(self, client, auth_header):
        """After hiding widgets, reset should restore defaults."""
        # Hide some widgets first
        client.patch("/dashboard/widgets", json={
            "updates": [
                {"id": "monthly_summary", "visible": False},
                {"id": "expense_chart", "visible": False},
            ]
        }, headers=auth_header)

        # Reset
        r = client.post("/dashboard/widgets/reset", headers=auth_header)
        assert r.status_code == 200
        widgets = r.get_json()["widgets"]

        monthly = next(w for w in widgets if w["id"] == "monthly_summary")
        chart = next(w for w in widgets if w["id"] == "expense_chart")
        assert monthly["visible"] is True
        assert chart["visible"] is True

    def test_reset_response_has_widgets_key(self, client, auth_header):
        r = client.post("/dashboard/widgets/reset", headers=auth_header)
        assert r.status_code == 200
        assert "widgets" in r.get_json()


class TestAvailableWidgets:
    """GET /dashboard/widgets/available tests."""

    def test_requires_auth(self, client):
        r = client.get("/dashboard/widgets/available")
        assert r.status_code == 401

    def test_returns_list_of_ids(self, client, auth_header):
        r = client.get("/dashboard/widgets/available", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "widget_ids" in data
        assert isinstance(data["widget_ids"], list)
        assert "monthly_summary" in data["widget_ids"]