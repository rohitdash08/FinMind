"""Tests for the savings goals feature (#133)."""
import json
from datetime import date, timedelta

import pytest
from app.extensions import db
from app.models import User
from app.routes.goals import SavingsGoal, SavingsMilestone, GoalStatus


@pytest.fixture
def seed_user(app):
    with app.app_context():
        user = User(email="goals-test@test.com", password_hash="hash", preferred_currency="USD")
        db.session.add(user)
        db.session.commit()
        yield user


class TestSavingsGoals:
    """Integration tests for savings goals CRUD and contributions."""

    def test_list_goals_empty(self, client, seed_user):
        resp = client.get(f"/api/savings-goals?user_id={seed_user.id}")
        assert resp.status_code == 200
        assert resp.json["goals"] == []

    def test_create_goal(self, client, seed_user):
        resp = client.post("/api/savings-goals", json={
            "user_id": seed_user.id,
            "name": "Emergency Fund",
            "target_amount": 10000,
            "currency": "USD",
        })
        assert resp.status_code == 201
        data = resp.json
        assert data["name"] == "Emergency Fund"
        assert data["target_amount"] == 10000.0
        assert data["current_amount"] == 0.0
        assert data["progress_pct"] == 0.0
        assert len(data["milestones"]) == 4  # 25%, 50%, 75%, 100%

    def test_create_goal_requires_fields(self, client, seed_user):
        resp = client.post("/api/savings-goals", json={"user_id": seed_user.id})
        assert resp.status_code == 400

    def test_contribute_to_goal(self, client, seed_user):
        goal_resp = client.post("/api/savings-goals", json={
            "user_id": seed_user.id, "name": "Vacation", "target_amount": 2000,
        })
        goal_id = goal_resp.json["id"]

        resp = client.post(f"/api/savings-goals/{goal_id}/contribute", json={"amount": 500})
        assert resp.status_code == 200
        assert resp.json["goal"]["current_amount"] == 500.0
        assert resp.json["goal"]["progress_pct"] == 25.0

    def test_milestone_detection(self, client, seed_user):
        goal_resp = client.post("/api/savings-goals", json={
            "user_id": seed_user.id, "name": "Car", "target_amount": 10000,
        })
        goal_id = goal_resp.json["id"]

        # Contribute 2500 (25% milestone)
        resp = client.post(f"/api/savings-goals/{goal_id}/contribute", json={"amount": 2500})
        milestones = resp.json["new_milestones"]
        assert "25% Complete" in milestones

        # Contribute 2500 more (50% milestone)
        resp = client.post(f"/api/savings-goals/{goal_id}/contribute", json={"amount": 2500})
        assert "Halfway There!" in resp.json["new_milestones"]

    def test_goal_completion(self, client, seed_user):
        goal_resp = client.post("/api/savings-goals", json={
            "user_id": seed_user.id, "name": "Small Goal", "target_amount": 100,
        })
        goal_id = goal_resp.json["id"]

        resp = client.post(f"/api/savings-goals/{goal_id}/contribute", json={"amount": 100})
        assert resp.json["goal"]["status"] == GoalStatus.COMPLETED.value
        assert "Goal Reached!" in resp.json["new_milestones"]

    def test_withdraw(self, client, seed_user):
        goal_resp = client.post("/api/savings-goals", json={
            "user_id": seed_user.id, "name": "Test Withdraw", "target_amount": 1000,
        })
        goal_id = goal_resp.json["id"]
        client.post(f"/api/savings-goals/{goal_id}/contribute", json={"amount": 500})
        resp = client.post(f"/api/savings-goals/{goal_id}/contribute", json={"amount": -200})
        assert resp.json["goal"]["current_amount"] == 300.0

    def test_delete_goal(self, client, seed_user):
        goal_resp = client.post("/api/savings-goals", json={
            "user_id": seed_user.id, "name": "Temp", "target_amount": 500,
        })
        goal_id = goal_resp.json["id"]
        resp = client.delete(f"/api/savings-goals/{goal_id}")
        assert resp.status_code == 200

    def test_summary_endpoint(self, client, seed_user):
        client.post("/api/savings-goals", json={
            "user_id": seed_user.id, "name": "Goal A", "target_amount": 1000,
        })
        client.post("/api/savings-goals", json={
            "user_id": seed_user.id, "name": "Goal B", "target_amount": 2000,
        })
        resp = client.get(f"/api/savings-goals/summary?user_id={seed_user.id}")
        assert resp.status_code == 200
        assert resp.json["total_goals"] == 2
        assert resp.json["total_target"] == 3000.0
