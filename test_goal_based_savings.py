"""
Tests for goal-based savings with milestones.
"""
import pytest
from datetime import datetime, date
from decimal import Decimal
from app.services.savings import (
    SavingsGoal,
    SavingsMilestone,
    SavingsDeposit,
    create_goal,
    deposit,
)
from app.extensions import db


class TestSavingsGoalModel:
    """Test SavingsGoal model."""

    def test_create_savings_goal(self, app, db):
        with app.app_context():
            goal = SavingsGoal(
                user_id=1,
                name="Emergency Fund",
                target_amount=Decimal("10000.00"),
                currency="USD"
            )
            db.session.add(goal)
            db.session.commit()

            saved = SavingsGoal.query.first()
            assert saved is not None
            assert saved.name == "Emergency Fund"
            assert saved.target_amount == Decimal("10000.00")
            assert saved.current_amount == Decimal("0")
            assert saved.currency == "USD"
            assert saved.status == "active"

    def test_progress_percent(self, app, db):
        with app.app_context():
            goal = SavingsGoal(
                user_id=1,
                name="Test Goal",
                target_amount=Decimal("1000.00"),
                current_amount=Decimal("500.00")
            )
            assert goal.progress_percent == 50.0

    def test_progress_percent_zero_target(self, app, db):
        with app.app_context():
            goal = SavingsGoal(
                user_id=1,
                name="Test Goal",
                target_amount=Decimal("0"),
                current_amount=Decimal("100.00")
            )
            assert goal.progress_percent == 0

    def test_progress_percent_over_100(self, app, db):
        with app.app_context():
            goal = SavingsGoal(
                user_id=1,
                name="Test Goal",
                target_amount=Decimal("1000.00"),
                current_amount=Decimal("1500.00")
            )
            assert goal.progress_percent == 100  # Capped at 100


class TestCreateGoalFunction:
    """Test create_goal function."""

    def test_create_goal_success(self, app, db):
        with app.app_context():
            goal = create_goal(
                user_id=1,
                name="Vacation Fund",
                target_amount=5000.00,
                currency="USD"
            )

            assert goal.id is not None
            assert goal.name == "Vacation Fund"
            assert goal.target_amount == Decimal("5000.00")
            assert goal.status == "active"

            # Check milestones were created
            milestones = SavingsMilestone.query.filter_by(goal_id=goal.id).all()
            assert len(milestones) == 4  # 25%, 50%, 75%, 100%

    def test_create_goal_invalid_amount(self, app, db):
        with app.app_context():
            with pytest.raises(ValueError, match="Target amount must be positive"):
                create_goal(
                    user_id=1,
                    name="Invalid Goal",
                    target_amount=-100.00
                )

    def test_create_goal_with_deadline(self, app, db):
        with app.app_context():
            deadline = date(2025, 12, 31)
            goal = create_goal(
                user_id=1,
                name="Year End Goal",
                target_amount=2000.00,
                deadline=deadline
            )

            assert goal.deadline == deadline


class TestDepositFunction:
    """Test deposit function."""

    def test_deposit_success(self, app, db):
        with app.app_context():
            goal = create_goal(user_id=1, name="Test Goal", target_amount=1000.00)
            
            result = deposit(goal_id=goal.id, user_id=1, amount=100.00)

            assert result["deposit_id"] is not None
            assert result["balance"] == 100.00
            assert result["progress"] == 10.0

    def test_deposit_multiple(self, app, db):
        with app.app_context():
            goal = create_goal(user_id=1, name="Test Goal", target_amount=1000.00)
            
            deposit(goal_id=goal.id, user_id=1, amount=100.00)
            result = deposit(goal_id=goal.id, user_id=1, amount=200.00)

            assert result["balance"] == 300.00
            assert result["progress"] == 30.0

    def test_deposit_reaches_milestone(self, app, db):
        with app.app_context():
            goal = create_goal(user_id=1, name="Test Goal", target_amount=1000.00)
            
            # Deposit 25% to reach first milestone
            deposit(goal_id=goal.id, user_id=1, amount=250.00)

            milestones = SavingsMilestone.query.filter_by(goal_id=goal.id, reached=True).all()
            assert len(milestones) == 1
            assert milestones[0].name == "25% reached"

    def test_deposit_completes_goal(self, app, db):
        with app.app_context():
            goal = create_goal(user_id=1, name="Test Goal", target_amount=1000.00)
            
            # Deposit full amount
            deposit(goal_id=goal.id, user_id=1, amount=1000.00)

            updated_goal = SavingsGoal.query.get(goal.id)
            assert updated_goal.status == "completed"
            assert updated_goal.completed_at is not None

    def test_deposit_invalid_amount(self, app, db):
        with app.app_context():
            goal = create_goal(user_id=1, name="Test Goal", target_amount=1000.00)
            
            with pytest.raises(ValueError, match="Deposit amount must be positive"):
                deposit(goal_id=goal.id, user_id=1, amount=-50.00)

    def test_deposit_wrong_user(self, app, db):
        with app.app_context():
            goal = create_goal(user_id=1, name="Test Goal", target_amount=1000.00)
            
            with pytest.raises(ValueError, match="Goal not found"):
                deposit(goal_id=goal.id, user_id=999, amount=100.00)

    def test_deposit_inactive_goal(self, app, db):
        with app.app_context():
            goal = create_goal(user_id=1, name="Test Goal", target_amount=1000.00)
            
            # Complete the goal first
            deposit(goal_id=goal.id, user_id=1, amount=1000.00)
            
            # Try to deposit to completed goal
            with pytest.raises(ValueError, match="Goal is not active"):
                deposit(goal_id=goal.id, user_id=1, amount=100.00)


@pytest.fixture
def app():
    """Create application for testing."""
    from app import create_app
    
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db(app):
    """Create database for testing."""
    with app.app_context():
        yield db
