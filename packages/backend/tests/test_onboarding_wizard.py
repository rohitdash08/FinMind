"""Tests for smart onboarding financial setup wizard (issue #101)."""
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
        user = User(email="onboard_test@example.com", password_hash=hashed)
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))

    return {"Authorization": f"Bearer {token}"}


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestWizardStatus:
    """GET /onboarding/status tests."""

    def test_requires_auth(self, client):
        r = client.get("/onboarding/status")
        assert r.status_code == 401

    def test_initial_state_is_goals(self, client, auth_header):
        r = client.get("/onboarding/status", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["current_step"] == "goals"
        assert data["completed_steps"] == []
        assert data["is_complete"] is False

    def test_status_has_steps_list(self, client, auth_header):
        r = client.get("/onboarding/status", headers=auth_header)
        data = r.get_json()
        assert "steps" in data
        assert "goals" in data["steps"]
        assert "complete" in data["steps"]


class TestWizardOptions:
    """GET /onboarding/options tests."""

    def test_requires_auth(self, client):
        r = client.get("/onboarding/options")
        assert r.status_code == 401

    def test_returns_goals_and_lifestyles(self, client, auth_header):
        r = client.get("/onboarding/options", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "goals" in data
        assert "lifestyles" in data
        assert "save_more" in data["goals"]
        assert "student" in data["lifestyles"]


class TestWizardSteps:
    """POST /onboarding/step/<step> tests."""

    def test_requires_auth(self, client):
        r = client.post("/onboarding/step/goals", json={"goals": ["save_more"]})
        assert r.status_code == 401

    def test_goals_step_advances_to_income(self, client, auth_header):
        r = client.post("/onboarding/step/goals", json={
            "goals": ["save_more", "track_spending"]
        }, headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["current_step"] == "income"
        assert "goals" in data["completed_steps"]

    def test_goals_step_empty_goals_returns_400(self, client, auth_header):
        r = client.post("/onboarding/step/goals", json={"goals": []}, headers=auth_header)
        assert r.status_code == 400

    def test_goals_step_invalid_goal_returns_400(self, client, auth_header):
        r = client.post("/onboarding/step/goals", json={
            "goals": ["not_a_real_goal"]
        }, headers=auth_header)
        assert r.status_code == 400

    def test_income_step_advances_to_lifestyle(self, client, auth_header):
        client.post("/onboarding/step/goals", json={"goals": ["save_more"]}, headers=auth_header)
        r = client.post("/onboarding/step/income", json={
            "monthly_income": 3000.0, "currency": "USD"
        }, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["current_step"] == "lifestyle"

    def test_income_missing_returns_400(self, client, auth_header):
        client.post("/onboarding/step/goals", json={"goals": ["save_more"]}, headers=auth_header)
        r = client.post("/onboarding/step/income", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_income_negative_returns_400(self, client, auth_header):
        client.post("/onboarding/step/goals", json={"goals": ["save_more"]}, headers=auth_header)
        r = client.post("/onboarding/step/income", json={"monthly_income": -100}, headers=auth_header)
        assert r.status_code == 400

    def test_lifestyle_step_advances_to_categories(self, client, auth_header):
        client.post("/onboarding/step/goals", json={"goals": ["save_more"]}, headers=auth_header)
        client.post("/onboarding/step/income", json={"monthly_income": 3000}, headers=auth_header)
        r = client.post("/onboarding/step/lifestyle", json={"lifestyle": "professional"}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["current_step"] == "categories"

    def test_lifestyle_invalid_returns_400(self, client, auth_header):
        client.post("/onboarding/step/goals", json={"goals": ["save_more"]}, headers=auth_header)
        client.post("/onboarding/step/income", json={"monthly_income": 3000}, headers=auth_header)
        r = client.post("/onboarding/step/lifestyle", json={"lifestyle": "billionaire"}, headers=auth_header)
        assert r.status_code == 400

    def test_categories_step_creates_categories(self, client, auth_header):
        client.post("/onboarding/step/goals", json={"goals": ["save_more"]}, headers=auth_header)
        client.post("/onboarding/step/income", json={"monthly_income": 3000}, headers=auth_header)
        client.post("/onboarding/step/lifestyle", json={"lifestyle": "student"}, headers=auth_header)
        r = client.post("/onboarding/step/categories", json={}, headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        # After categories step, wizard should be complete
        assert data["current_step"] == "complete"
        assert data["is_complete"] is True

    def test_categories_step_with_custom_categories(self, client, auth_header):
        client.post("/onboarding/step/goals", json={"goals": ["save_more"]}, headers=auth_header)
        client.post("/onboarding/step/income", json={"monthly_income": 3000}, headers=auth_header)
        client.post("/onboarding/step/lifestyle", json={"lifestyle": "professional"}, headers=auth_header)
        r = client.post("/onboarding/step/categories", json={
            "categories": ["Custom Cat 1", "Custom Cat 2"]
        }, headers=auth_header)
        assert r.status_code == 200
        assert "categories_created" in r.get_json()["data"]

    def test_invalid_step_name_returns_400(self, client, auth_header):
        r = client.post("/onboarding/step/nonexistent", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_data_persists_in_status(self, client, auth_header):
        """Goals step advances correctly and persists current_step."""
        r = client.post("/onboarding/step/goals", json={"goals": ["invest"]}, headers=auth_header)
        assert r.status_code == 200
        # Step response includes advanced state
        data = r.get_json()
        assert data["current_step"] == "income"
        assert "goals" in data["completed_steps"]
        assert data["data"].get("goals") == ["invest"]


class TestWizardReset:
    """POST /onboarding/reset tests."""

    def test_requires_auth(self, client):
        r = client.post("/onboarding/reset")
        assert r.status_code == 401

    def test_reset_clears_state(self, client, auth_header):
        # Complete some steps
        client.post("/onboarding/step/goals", json={"goals": ["save_more"]}, headers=auth_header)
        client.post("/onboarding/step/income", json={"monthly_income": 3000}, headers=auth_header)

        # Reset
        r = client.post("/onboarding/reset", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["current_step"] == "goals"
        assert data["completed_steps"] == []
        assert data["is_complete"] is False