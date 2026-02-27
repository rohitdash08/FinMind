"""Tests for Personal Financial Digital Twin."""

import pytest
from app.services.digital_twin import (
    get_profile, update_profile, get_snapshot, simulate,
    list_simulations, get_simulation, delete_simulation, SCENARIO_TYPES,
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
def profile(app, user):
    with app.app_context():
        return update_profile(user, monthly_income=5000, monthly_fixed_expenses=2000, savings_rate=20)


class TestProfile:
    def test_default(self, app, user):
        with app.app_context():
            p = get_profile(user)
            assert p["monthly_income"] == 0

    def test_update(self, app, user):
        with app.app_context():
            p = update_profile(user, monthly_income=5000, risk_tolerance="high")
            assert p["monthly_income"] == 5000
            assert p["risk_tolerance"] == "high"


class TestSnapshot:
    def test_basic(self, app, user, profile):
        with app.app_context():
            s = get_snapshot(user)
            assert s["monthly_income"] == 5000
            assert "avg_daily_spend" in s
            assert "projected_monthly_savings" in s


class TestSimulations:
    def test_income_change(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Raise", "income_change", {"new_income": 7000, "months": 6})
            assert r["results"]["monthly_diff"] == 2000
            assert len(r["results"]["projections"]) == 6

    def test_expense_reduction(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Cut costs", "expense_reduction", {"reduction_pct": 20, "months": 12})
            assert r["results"]["monthly_saved"] == 400

    def test_major_purchase(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Car", "major_purchase", {"cost": 30000})
            assert r["results"]["feasible"] is True
            assert r["results"]["months_needed"] > 0

    def test_emergency_fund(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Emergency", "emergency_fund", {"target_months": 6})
            assert r["results"]["target_amount"] == 12000

    def test_savings_goal(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Vacation", "savings_goal", {"target": 5000, "months": 24})
            assert r["results"]["months_needed"] > 0

    def test_investment(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Invest", "investment_return",
                         {"principal": 10000, "annual_return_pct": 8, "months": 12})
            assert r["results"]["final_balance"] > 10000

    def test_debt_payoff(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Debt", "debt_payoff",
                         {"debt": 10000, "annual_rate_pct": 6, "monthly_payment": 500})
            assert r["results"]["months_to_payoff"] > 0

    def test_retirement(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Retire", "retirement",
                         {"current_savings": 50000, "monthly_contribution": 1000, "years": 30})
            assert r["results"]["final_balance"] > 50000

    def test_invalid_scenario(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                simulate(user, "Bad", "nonexistent", {})

    def test_list(self, app, user, profile):
        with app.app_context():
            simulate(user, "A", "income_change", {"new_income": 6000})
            simulate(user, "B", "major_purchase", {"cost": 1000})
            sims = list_simulations(user)
            assert len(sims) == 2

    def test_get(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Test", "income_change", {"new_income": 6000})
            s = get_simulation(user, r["id"])
            assert s["name"] == "Test"

    def test_get_not_found(self, app, user):
        with app.app_context():
            assert get_simulation(user, 9999) is None

    def test_delete(self, app, user, profile):
        with app.app_context():
            r = simulate(user, "Del", "income_change", {"new_income": 6000})
            assert delete_simulation(user, r["id"]) is True

    def test_delete_not_found(self, app, user):
        with app.app_context():
            assert delete_simulation(user, 9999) is False


class TestAPI:
    def test_profile(self, app, user, token):
        client = app.test_client()
        resp = client.get("/twin/profile", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_update_profile(self, app, user, token):
        client = app.test_client()
        resp = client.put("/twin/profile", json={"monthly_income": 5000},
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_snapshot(self, app, user, token):
        client = app.test_client()
        resp = client.get("/twin/snapshot", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_scenarios(self, app, user, token):
        client = app.test_client()
        resp = client.get("/twin/scenarios", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_simulate(self, app, user, token):
        client = app.test_client()
        client.put("/twin/profile", json={"monthly_income": 5000, "monthly_fixed_expenses": 2000},
                   headers={"Authorization": f"Bearer {token}"})
        resp = client.post("/twin/simulate",
                           json={"name": "Test", "scenario_type": "income_change",
                                 "parameters": {"new_income": 7000}},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_list_sims(self, app, user, token):
        client = app.test_client()
        resp = client.get("/twin/simulations", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
