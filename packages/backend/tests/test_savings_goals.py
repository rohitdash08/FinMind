"""Tests for savings goal tracking service."""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.services.savings_goals import (
    create_goal,
    add_contribution,
    get_goal,
    list_goals,
    projected_completion,
    SavingsGoal,
    GoalMilestone,
    GoalContribution,
)


class TestCreateGoal:
    @pytest.fixture(autouse=True)
    def setup(self, app, db_session, test_user):
        self.user_id = test_user.id

    def test_creates_goal_with_milestones(self, app):
        with app.app_context():
            result = create_goal(self.user_id, "Emergency Fund", 10000.0)
            assert result["name"] == "Emergency Fund"
            assert result["target_amount"] == 10000.0
            assert result["current_amount"] == 0.0
            assert result["progress_pct"] == 0.0
            assert result["status"] == "active"
            assert len(result["milestones"]) == 4
            assert result["milestones"][0]["target_percentage"] == 25
            assert result["milestones"][3]["target_percentage"] == 100

    def test_creates_goal_with_deadline(self, app):
        with app.app_context():
            deadline = date.today() + timedelta(days=365)
            result = create_goal(self.user_id, "Vacation", 5000.0, deadline=deadline)
            assert result["deadline"] == deadline.isoformat()

    def test_creates_goal_with_custom_currency(self, app):
        with app.app_context():
            result = create_goal(self.user_id, "New Car", 20000.0, currency="USD")
            assert result["currency"] == "USD"


class TestAddContribution:
    @pytest.fixture(autouse=True)
    def setup(self, app, db_session, test_user):
        self.user_id = test_user.id
        with app.app_context():
            self.goal = create_goal(self.user_id, "Test Goal", 1000.0)

    def test_adds_contribution(self, app):
        with app.app_context():
            result = add_contribution(self.goal["id"], self.user_id, 100.0)
            assert result["new_total"] == 100.0
            assert result["progress_pct"] == 10.0
            assert result["goal_completed"] is False

    def test_reaches_milestone_at_25_pct(self, app):
        with app.app_context():
            result = add_contribution(self.goal["id"], self.user_id, 250.0)
            assert "Quarter way" in result["milestones_reached"]

    def test_multiple_milestones_in_one_contribution(self, app):
        with app.app_context():
            result = add_contribution(self.goal["id"], self.user_id, 750.0)
            assert "Quarter way" in result["milestones_reached"]
            assert "Halfway" in result["milestones_reached"]
            assert "Almost there" in result["milestones_reached"]

    def test_goal_completes_at_target(self, app):
        with app.app_context():
            result = add_contribution(self.goal["id"], self.user_id, 1000.0)
            assert result["goal_completed"] is True
            assert "Goal reached!" in result["milestones_reached"]

    def test_contribution_to_nonexistent_goal(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match="not found"):
                add_contribution(9999, self.user_id, 50.0)

    def test_contribution_with_notes(self, app):
        with app.app_context():
            result = add_contribution(self.goal["id"], self.user_id, 50.0, notes="Birthday money")
            assert result["new_total"] == 50.0


class TestListGoals:
    @pytest.fixture(autouse=True)
    def setup(self, app, db_session, test_user):
        self.user_id = test_user.id

    def test_list_empty(self, app):
        with app.app_context():
            goals = list_goals(self.user_id)
            assert goals == []

    def test_list_multiple(self, app):
        with app.app_context():
            create_goal(self.user_id, "Goal 1", 1000.0)
            create_goal(self.user_id, "Goal 2", 2000.0)
            goals = list_goals(self.user_id)
            assert len(goals) == 2

    def test_filter_by_status(self, app):
        with app.app_context():
            g = create_goal(self.user_id, "Small Goal", 10.0)
            add_contribution(g["id"], self.user_id, 10.0)
            create_goal(self.user_id, "Big Goal", 10000.0)
            active = list_goals(self.user_id, status="active")
            completed = list_goals(self.user_id, status="completed")
            assert len(active) == 1
            assert len(completed) == 1


class TestGetGoal:
    @pytest.fixture(autouse=True)
    def setup(self, app, db_session, test_user):
        self.user_id = test_user.id

    def test_get_existing_goal(self, app):
        with app.app_context():
            created = create_goal(self.user_id, "My Goal", 5000.0)
            fetched = get_goal(created["id"], self.user_id)
            assert fetched is not None
            assert fetched["name"] == "My Goal"

    def test_get_nonexistent_goal(self, app):
        with app.app_context():
            assert get_goal(9999, self.user_id) is None

    def test_cannot_access_other_users_goal(self, app):
        with app.app_context():
            created = create_goal(self.user_id, "Private", 1000.0)
            assert get_goal(created["id"], self.user_id + 999) is None
