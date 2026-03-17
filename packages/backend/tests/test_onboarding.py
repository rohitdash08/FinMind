"""
Tests for Smart Onboarding Financial Setup Wizard (Issue #101).

Covers:
- GET /onboarding/steps returns ordered list
- GET /onboarding/steps/<name> returns full step definition
- GET /onboarding/steps/unknown returns 404
- POST /onboarding/validate/<step> valid answers → {valid: true}
- POST /onboarding/validate/<step> missing required → {valid: false, errors}
- POST /onboarding/complete success → 201 + categories created
- POST /onboarding/complete missing answers → 400
- POST /onboarding/complete validation failure → 400
- Categories created in DB after complete
- complete is idempotent (re-running doesn't duplicate categories)
- Budget recommendation fields present
- Tips returned
- Auth required on all endpoints
- User isolation (complete creates categories for own user only)
- Unit tests: get_step, validate_step_answers, complete_onboarding, _build_budget_recommendations
"""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models import Category
from app.services.onboarding import (
    STEPS,
    complete_onboarding,
    get_step,
    validate_step_answers,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="ob@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


_VALID_ANSWERS = {
    "profile": {
        "income_range": "mid",
        "housing": "rent",
        "dependents": "0",
    },
    "goals": {
        "primary_goals": ["emergency_fund", "reduce_spending"],
    },
    "spending": {
        "categories": ["food", "transport", "utilities"],
    },
    "budget_method": {
        "method": "50_30_20",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — service
# ─────────────────────────────────────────────────────────────────────────────

class TestGetStep:
    def test_known_step_returns_definition(self):
        step = get_step("profile")
        assert step is not None
        assert step["step"] == "profile"
        assert "fields" in step
        assert "next_step" in step

    def test_unknown_step_returns_none(self):
        assert get_step("nonexistent") is None

    def test_all_steps_defined(self):
        for s in STEPS:
            assert get_step(s) is not None

    def test_complete_step_has_no_next(self):
        assert get_step("complete")["next_step"] is None


class TestValidateStepAnswers:
    def test_valid_profile(self):
        errors = validate_step_answers("profile", {"income_range": "mid", "housing": "rent"})
        assert errors == []

    def test_missing_required_field(self):
        errors = validate_step_answers("profile", {"housing": "rent"})  # missing income_range
        assert any("income_range" in e for e in errors)

    def test_unknown_step_returns_error(self):
        errors = validate_step_answers("mystery_step", {})
        assert len(errors) > 0

    def test_valid_goals(self):
        errors = validate_step_answers("goals", {"primary_goals": ["invest"]})
        assert errors == []

    def test_missing_goals(self):
        errors = validate_step_answers("goals", {})
        assert len(errors) > 0


class TestCompleteOnboarding:
    def _make_user(self, app_fixture, email):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email=email, password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            return u.id

    def test_complete_creates_categories(self, app_fixture):
        uid = self._make_user(app_fixture, "ob_cats@test.com")
        with app_fixture.app_context():
            result = complete_onboarding(uid, _VALID_ANSWERS)
            cats_after = db.session.query(Category).filter_by(user_id=uid).count()

        assert len(result["categories_created"]) == 3
        assert cats_after == 3

    def test_complete_idempotent(self, app_fixture):
        uid = self._make_user(app_fixture, "ob_idem@test.com")
        with app_fixture.app_context():
            complete_onboarding(uid, _VALID_ANSWERS)
            complete_onboarding(uid, _VALID_ANSWERS)  # second call
            cats = db.session.query(Category).filter_by(user_id=uid).count()
        assert cats == 3  # no duplicates

    def test_budget_recommendation_fields(self, app_fixture):
        uid = self._make_user(app_fixture, "ob_budget@test.com")
        with app_fixture.app_context():
            result = complete_onboarding(uid, _VALID_ANSWERS)
        rec = result["budget_recommendation"]
        for k in ("needs_budget", "wants_budget", "savings_budget", "method"):
            assert k in rec

    def test_tips_returned(self, app_fixture):
        uid = self._make_user(app_fixture, "ob_tips@test.com")
        with app_fixture.app_context():
            result = complete_onboarding(uid, _VALID_ANSWERS)
        assert isinstance(result["tips"], list)
        assert len(result["tips"]) >= 1

    def test_savings_boost_for_emergency_fund_goal(self, app_fixture):
        uid = self._make_user(app_fixture, "ob_boost@test.com")
        answers_boost = dict(_VALID_ANSWERS)
        answers_boost["goals"] = {"primary_goals": ["emergency_fund", "pay_debt", "invest"]}
        with app_fixture.app_context():
            result = complete_onboarding(uid, answers_boost)
        rec = result["budget_recommendation"]
        # With multiple savings goals, savings_pct should be > 20%
        assert rec["savings_pct"] > 20.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestOnboardingStepsEndpoints:
    def test_list_steps_requires_auth(self, client, app_fixture):
        assert client.get("/onboarding/steps").status_code == 401

    def test_list_steps_returns_all(self, client, app_fixture):
        h = _auth(client, "obs1@test.com")
        r = client.get("/onboarding/steps", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert "steps" in d
        assert set(d["steps"]) == set(STEPS)

    def test_get_step_def_valid(self, client, app_fixture):
        h = _auth(client, "obs2@test.com")
        r = client.get("/onboarding/steps/profile", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert d["step"] == "profile"
        assert "fields" in d

    def test_get_step_def_unknown_returns_404(self, client, app_fixture):
        h = _auth(client, "obs3@test.com")
        assert client.get("/onboarding/steps/whatever", headers=h).status_code == 404

    def test_all_steps_accessible(self, client, app_fixture):
        h = _auth(client, "obs4@test.com")
        for step in STEPS:
            r = client.get(f"/onboarding/steps/{step}", headers=h)
            assert r.status_code == 200


class TestOnboardingValidateEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.post("/onboarding/validate/profile", json={}).status_code == 401

    def test_valid_answers(self, client, app_fixture):
        h = _auth(client, "obv1@test.com")
        r = client.post("/onboarding/validate/profile",
                        json={"answers": {"income_range": "mid", "housing": "rent"}},
                        headers=h)
        assert r.status_code == 200
        assert r.get_json()["valid"] is True

    def test_missing_required_answers(self, client, app_fixture):
        h = _auth(client, "obv2@test.com")
        r = client.post("/onboarding/validate/profile",
                        json={"answers": {}},
                        headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert d["valid"] is False
        assert len(d["errors"]) > 0

    def test_non_dict_answers_returns_400(self, client, app_fixture):
        h = _auth(client, "obv3@test.com")
        r = client.post("/onboarding/validate/profile",
                        json={"answers": "bad"},
                        headers=h)
        assert r.status_code == 400


class TestOnboardingCompleteEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.post("/onboarding/complete", json={}).status_code == 401

    def test_complete_success(self, client, app_fixture):
        h = _auth(client, "obc1@test.com")
        r = client.post("/onboarding/complete",
                        json={"answers": _VALID_ANSWERS},
                        headers=h)
        assert r.status_code == 201
        d = r.get_json()
        assert d["status"] == "complete"
        assert isinstance(d["categories_created"], list)
        assert "budget_recommendation" in d
        assert "tips" in d
        assert "next_steps" in d

    def test_missing_answers_returns_400(self, client, app_fixture):
        h = _auth(client, "obc2@test.com")
        r = client.post("/onboarding/complete", json={}, headers=h)
        assert r.status_code == 400

    def test_validation_failure_returns_400(self, client, app_fixture):
        h = _auth(client, "obc3@test.com")
        bad_answers = dict(_VALID_ANSWERS)
        bad_answers["profile"] = {}  # missing required fields
        r = client.post("/onboarding/complete",
                        json={"answers": bad_answers},
                        headers=h)
        assert r.status_code == 400
        d = r.get_json()
        assert "details" in d

    def test_categories_created_in_db(self, client, app_fixture):
        h = _auth(client, "obc4@test.com")
        uid = _get_uid(app_fixture, "obc4@test.com")
        client.post("/onboarding/complete",
                    json={"answers": _VALID_ANSWERS},
                    headers=h)
        with app_fixture.app_context():
            cats = db.session.query(Category).filter_by(user_id=uid).all()
        assert len(cats) == 3

    def test_idempotent_no_duplicate_categories(self, client, app_fixture):
        h = _auth(client, "obc5@test.com")
        uid = _get_uid(app_fixture, "obc5@test.com")
        client.post("/onboarding/complete", json={"answers": _VALID_ANSWERS}, headers=h)
        client.post("/onboarding/complete", json={"answers": _VALID_ANSWERS}, headers=h)
        with app_fixture.app_context():
            cats = db.session.query(Category).filter_by(user_id=uid).all()
        assert len(cats) == 3  # no duplicates

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "obc_iso1@test.com")
        h2 = _auth(client, "obc_iso2@test.com")
        uid2 = _get_uid(app_fixture, "obc_iso2@test.com")

        client.post("/onboarding/complete", json={"answers": _VALID_ANSWERS}, headers=h1)

        with app_fixture.app_context():
            cats2 = db.session.query(Category).filter_by(user_id=uid2).all()
        assert len(cats2) == 0
