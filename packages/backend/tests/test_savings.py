"""Savings goals unit tests"""
import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal


class TestSavingsGoalModel:
    def test_create_goal(self, app, test_user, db):
        from packages.backend.app.models import SavingsGoal, GoalStatus
        with app.app_context():
            goal = SavingsGoal(user_id=test_user["id"], name="Vacation Fund", target_amount=Decimal("10000.00"))
            db.session.add(goal)
            db.session.commit()
            assert goal.id is not None
            assert goal.progress_percentage == 0.0

    def test_progress_percentage(self, app, test_user, db):
        from packages.backend.app.models import SavingsGoal
        with app.app_context():
            goal = SavingsGoal(user_id=test_user["id"], name="Test", target_amount=Decimal("10000.00"), current_amount=Decimal("2500.00"))
            db.session.add(goal)
            db.session.commit()
            assert goal.progress_percentage == 25.0

    def test_is_completed(self, app, test_user, db):
        from packages.backend.app.models import SavingsGoal
        with app.app_context():
            goal = SavingsGoal(user_id=test_user["id"], name="Done", target_amount=Decimal("10000.00"), current_amount=Decimal("10000.00"))
            db.session.add(goal)
            db.session.commit()
            assert goal.is_completed() is True


class TestSavingsContribution:
    def test_create_contribution(self, app, test_user, db):
        from packages.backend.app.models import SavingsGoal, SavingsContribution
        with app.app_context():
            goal = SavingsGoal(user_id=test_user["id"], name="Test", target_amount=Decimal("10000.00"))
            db.session.add(goal)
            db.session.commit()
            contrib = SavingsContribution(goal_id=goal.id, amount=Decimal("1000.00"), note="First")
            db.session.add(contrib)
            db.session.commit()
            assert contrib.id is not None


@pytest.fixture
def app():
    from packages.backend.app import create_app
    app = create_app(TestSettings())
    app.config["TESTING"] = True
    return app


@pytest.fixture
def test_user(app):
    from packages.backend.app.extensions import db
    from packages.backend.app.models import User
    with app.app_context():
        user = User(email="test@example.com", password_hash="hash", preferred_currency="INR")
        db.session.add(user)
        db.session.commit()
        yield {"id": user.id}


@pytest.fixture
def db(app):
    from packages.backend.app.extensions import db as _db
    return _db


class TestSettings:
    database_url = "sqlite:///:memory:"
    jwt_secret = "test"
    jwt_access_minutes = 30
    jwt_refresh_hours = 24
    openai_api_key = ""
    gemini_api_key = ""
    gemini_model = "gemini-1.5-flash"
    twilio_account_sid = ""
    twilio_auth_token = ""
    twilio_whatsapp_from = ""
    email_from = "test@example.com"
