"""
Tests for goal-based savings tracking.
"""

import pytest
from app.services.savings import (
    create_goal,
    add_contribution,
    get_user_goals,
    get_goals_overview,
    withdraw_from_goal,
)


class TestGoalCreation:
    def test_create_basic(self, app, db_session):
        with app.app_context():
            goal = create_goal(1, "Emergency Fund", 10000)
            assert goal.name == "Emergency Fund"
            assert goal.target_amount == 10000
            assert goal.current_amount == 0
            assert not goal.is_completed

    def test_create_with_deadline(self, app, db_session):
        with app.app_context():
            from datetime import datetime, timedelta
            deadline = datetime.utcnow() + timedelta(days=365)
            goal = create_goal(1, "Vacation", 5000, deadline=deadline, category="vacation")
            assert goal.category == "vacation"
            assert goal.deadline is not None

    def test_invalid_amount(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                create_goal(1, "Bad", -100)

    def test_invalid_category(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                create_goal(1, "Bad", 1000, category="invalid")

    def test_default_milestones(self, app, db_session):
        with app.app_context():
            goal = create_goal(1, "Test", 1000)
            milestones = goal.milestones.all()
            assert len(milestones) == 4
            pcts = [m.percentage for m in milestones]
            assert pcts == [25, 50, 75, 100]


class TestContributions:
    def test_add_contribution(self, app, db_session):
        with app.app_context():
            goal = create_goal(1, "Test", 1000)
            contrib, milestones = add_contribution(goal.id, 1, 200, "First deposit")
            assert contrib.amount == 200
            assert len(milestones) == 0  # 20% < 25%

    def test_reach_milestone(self, app, db_session):
        with app.app_context():
            goal = create_goal(1, "Test", 1000)
            contrib, milestones = add_contribution(goal.id, 1, 250)
            assert len(milestones) == 1
            assert milestones[0].percentage == 25

    def test_complete_goal(self, app, db_session):
        with app.app_context():
            goal = create_goal(1, "Test", 1000)
            contrib, milestones = add_contribution(goal.id, 1, 1000)
            assert goal.is_completed
            assert len(milestones) == 4  # All milestones reached

    def test_negative_contribution(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                goal = create_goal(1, "Test", 1000)
                add_contribution(goal.id, 1, -100)


class TestWithdrawal:
    def test_withdraw(self, app, db_session):
        with app.app_context():
            goal = create_goal(1, "Test", 1000)
            add_contribution(goal.id, 1, 500)
            withdraw_from_goal(goal.id, 1, 200)
            assert goal.current_amount == 300

    def test_overdraw(self, app, db_session):
        with app.app_context():
            goal = create_goal(1, "Test", 1000)
            add_contribution(goal.id, 1, 100)
            with pytest.raises(ValueError):
                withdraw_from_goal(goal.id, 1, 200)


class TestOverview:
    def test_overview(self, app, db_session):
        with app.app_context():
            create_goal(1, "Fund A", 5000, category="emergency")
            create_goal(1, "Fund B", 3000, category="vacation")
            g = create_goal(1, "Fund C", 2000, category="car")
            add_contribution(g.id, 1, 1000)

            overview = get_goals_overview(1)
            assert overview["total_goals"] == 3
            assert overview["total_saved"] == 1000
            assert overview["overall_progress"] > 0
