"""Tests for Goal-based Savings Tracking & Milestones.

Covers:
- Goal CRUD (create, list, get, update, delete)
- Contribution workflow and balance updates
- Milestone auto-creation and progression
- Goal auto-completion at 100%
- Summary endpoint
- Status filtering
- Validation and auth
"""

import pytest
from app.extensions import db
from app.models import SavingsGoal, GoalContribution, GoalMilestone, GoalStatus


def _register_and_login(client, email="goals@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_goal(client, hdr, name="Vacation Fund", target=1000, **kwargs):
    data = {"name": name, "target_amount": target, **kwargs}
    return client.post("/goals", headers=hdr, json=data)


# ---------------------------------------------------------------------------
# Goal CRUD
# ---------------------------------------------------------------------------

class TestGoalCRUD:
    def test_create_goal(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=5000)
        assert r.status_code == 201
        goal = r.get_json()["goal"]
        assert goal["name"] == "Vacation Fund"
        assert goal["target_amount"] == 5000
        assert goal["current_amount"] == 0
        assert goal["progress_pct"] == 0
        assert goal["status"] == "ACTIVE"
        # Default milestones created
        assert len(goal["milestones"]) == 4
        pcts = [m["percentage"] for m in goal["milestones"]]
        assert pcts == [25, 50, 75, 100]

    def test_list_goals(self, app_fixture, client):
        hdr = _register_and_login(client)
        _create_goal(client, hdr, name="Goal A")
        _create_goal(client, hdr, name="Goal B")

        r = client.get("/goals", headers=hdr)
        assert r.status_code == 200
        goals = r.get_json()["goals"]
        assert len(goals) == 2

    def test_get_goal_detail(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr)
        gid = r.get_json()["goal"]["id"]

        r = client.get(f"/goals/{gid}", headers=hdr)
        assert r.status_code == 200
        goal = r.get_json()["goal"]
        assert "contributions" in goal
        assert "milestones" in goal

    def test_update_goal(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr)
        gid = r.get_json()["goal"]["id"]

        r = client.put(f"/goals/{gid}", headers=hdr,
                       json={"name": "New Car", "target_amount": 20000})
        assert r.status_code == 200
        assert r.get_json()["goal"]["name"] == "New Car"
        assert r.get_json()["goal"]["target_amount"] == 20000

    def test_delete_goal(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr)
        gid = r.get_json()["goal"]["id"]

        r = client.delete(f"/goals/{gid}", headers=hdr)
        assert r.status_code == 200

        r = client.get(f"/goals/{gid}", headers=hdr)
        assert r.status_code == 404

    def test_goal_not_found(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.get("/goals/9999", headers=hdr)
        assert r.status_code == 404

    def test_create_requires_name_and_target(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.post("/goals", headers=hdr, json={})
        assert r.status_code == 400

    def test_create_requires_auth(self, client):
        r = client.post("/goals", json={"name": "Test", "target_amount": 100})
        assert r.status_code == 401

    def test_status_filter(self, app_fixture, client):
        hdr = _register_and_login(client)
        _create_goal(client, hdr, name="Active Goal")
        r = _create_goal(client, hdr, name="Paused Goal")
        gid = r.get_json()["goal"]["id"]
        client.put(f"/goals/{gid}", headers=hdr, json={"status": "PAUSED"})

        r = client.get("/goals?status=ACTIVE", headers=hdr)
        goals = r.get_json()["goals"]
        assert len(goals) == 1
        assert goals[0]["name"] == "Active Goal"


# ---------------------------------------------------------------------------
# Contributions
# ---------------------------------------------------------------------------

class TestContributions:
    def test_contribute_to_goal(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=1000)
        gid = r.get_json()["goal"]["id"]

        r = client.post(f"/goals/{gid}/contribute", headers=hdr,
                        json={"amount": 250, "notes": "First deposit"})
        assert r.status_code == 201
        body = r.get_json()
        assert body["contribution"]["amount"] == 250
        assert body["goal"]["current_amount"] == 250
        assert body["goal"]["progress_pct"] == 25.0

    def test_multiple_contributions(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=1000)
        gid = r.get_json()["goal"]["id"]

        client.post(f"/goals/{gid}/contribute", headers=hdr,
                    json={"amount": 300})
        r = client.post(f"/goals/{gid}/contribute", headers=hdr,
                        json={"amount": 200})
        assert r.get_json()["goal"]["current_amount"] == 500
        assert r.get_json()["goal"]["progress_pct"] == 50.0

    def test_cannot_contribute_to_paused_goal(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=1000)
        gid = r.get_json()["goal"]["id"]
        client.put(f"/goals/{gid}", headers=hdr, json={"status": "PAUSED"})

        r = client.post(f"/goals/{gid}/contribute", headers=hdr,
                        json={"amount": 100})
        assert r.status_code == 400

    def test_contribution_requires_amount(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=1000)
        gid = r.get_json()["goal"]["id"]

        r = client.post(f"/goals/{gid}/contribute", headers=hdr, json={})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

class TestMilestones:
    def test_milestone_auto_reached(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=100)
        gid = r.get_json()["goal"]["id"]

        # Contribute 25 → 25% milestone
        r = client.post(f"/goals/{gid}/contribute", headers=hdr,
                        json={"amount": 25})
        reached = r.get_json()["milestones_reached"]
        assert len(reached) == 1
        assert reached[0]["percentage"] == 25

    def test_multiple_milestones_at_once(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=100)
        gid = r.get_json()["goal"]["id"]

        # Contribute 60 → both 25% and 50% milestones
        r = client.post(f"/goals/{gid}/contribute", headers=hdr,
                        json={"amount": 60})
        reached = r.get_json()["milestones_reached"]
        pcts = [m["percentage"] for m in reached]
        assert 25 in pcts
        assert 50 in pcts

    def test_goal_auto_completes_at_100(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=100)
        gid = r.get_json()["goal"]["id"]

        r = client.post(f"/goals/{gid}/contribute", headers=hdr,
                        json={"amount": 100})
        goal = r.get_json()["goal"]
        assert goal["status"] == "COMPLETED"
        assert goal["completed_at"] is not None

    def test_list_milestones(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = _create_goal(client, hdr, target=100)
        gid = r.get_json()["goal"]["id"]

        r = client.get(f"/goals/{gid}/milestones", headers=hdr)
        assert r.status_code == 200
        milestones = r.get_json()["milestones"]
        assert len(milestones) == 4
        assert all(m["reached"] is False for m in milestones)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_with_goals(self, app_fixture, client):
        hdr = _register_and_login(client)
        _create_goal(client, hdr, name="Goal A", target=1000)
        r = _create_goal(client, hdr, name="Goal B", target=500)
        gid = r.get_json()["goal"]["id"]
        client.post(f"/goals/{gid}/contribute", headers=hdr,
                    json={"amount": 500})  # completes Goal B

        r = client.get("/goals/summary", headers=hdr)
        assert r.status_code == 200
        s = r.get_json()["summary"]
        assert s["total_goals"] == 2
        assert s["active_goals"] == 1
        assert s["completed_goals"] == 1
        assert s["total_saved"] == 500

    def test_empty_summary(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.get("/goals/summary", headers=hdr)
        assert r.status_code == 200
        s = r.get_json()["summary"]
        assert s["total_goals"] == 0
        assert s["overall_progress_pct"] == 0
