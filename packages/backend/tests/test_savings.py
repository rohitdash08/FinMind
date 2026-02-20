"""Tests for savings goals and milestones."""
import pytest


class TestSavingsGoals:
    """CRUD tests for /savings/goals."""

    def test_create_goal(self, client, auth_header):
        r = client.post(
            "/savings/goals",
            json={"name": "Emergency Fund", "target_amount": 10000, "currency": "USD", "deadline": "2026-12-31"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Emergency Fund"
        assert data["target_amount"] == 10000.0
        assert data["current_amount"] == 0.0
        assert data["currency"] == "USD"
        assert data["deadline"] == "2026-12-31"
        assert data["progress_pct"] == 0.0

    def test_create_goal_missing_name(self, client, auth_header):
        r = client.post("/savings/goals", json={"target_amount": 100}, headers=auth_header)
        assert r.status_code == 400

    def test_create_goal_bad_amount(self, client, auth_header):
        r = client.post("/savings/goals", json={"name": "X", "target_amount": -5}, headers=auth_header)
        assert r.status_code == 400

    def test_list_goals(self, client, auth_header):
        client.post("/savings/goals", json={"name": "A", "target_amount": 100}, headers=auth_header)
        client.post("/savings/goals", json={"name": "B", "target_amount": 200}, headers=auth_header)
        r = client.get("/savings/goals", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_update_goal_add_funds(self, client, auth_header):
        r = client.post("/savings/goals", json={"name": "Car", "target_amount": 1000}, headers=auth_header)
        goal_id = r.get_json()["id"]
        r = client.put(f"/savings/goals/{goal_id}", json={"add_funds": 250}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["current_amount"] == 250.0
        assert r.get_json()["progress_pct"] == 25.0

    def test_update_goal_edit_name(self, client, auth_header):
        r = client.post("/savings/goals", json={"name": "Old", "target_amount": 100}, headers=auth_header)
        goal_id = r.get_json()["id"]
        r = client.put(f"/savings/goals/{goal_id}", json={"name": "New"}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"

    def test_update_goal_not_found(self, client, auth_header):
        r = client.put("/savings/goals/9999", json={"name": "X"}, headers=auth_header)
        assert r.status_code == 404

    def test_delete_goal(self, client, auth_header):
        r = client.post("/savings/goals", json={"name": "Del", "target_amount": 50}, headers=auth_header)
        goal_id = r.get_json()["id"]
        r = client.delete(f"/savings/goals/{goal_id}", headers=auth_header)
        assert r.status_code == 200
        r = client.get("/savings/goals", headers=auth_header)
        assert len(r.get_json()) == 0

    def test_delete_goal_not_found(self, client, auth_header):
        r = client.delete("/savings/goals/9999", headers=auth_header)
        assert r.status_code == 404


class TestMilestones:
    """Milestone auto-creation and tracking."""

    def test_milestones_auto_created(self, client, auth_header):
        r = client.post("/savings/goals", json={"name": "M", "target_amount": 1000}, headers=auth_header)
        goal_id = r.get_json()["id"]
        r = client.get(f"/savings/goals/{goal_id}/milestones", headers=auth_header)
        assert r.status_code == 200
        ms = r.get_json()
        assert len(ms) == 4
        amounts = [m["amount"] for m in ms]
        assert amounts == [250.0, 500.0, 750.0, 1000.0]
        assert all(m["reached_at"] is None for m in ms)

    def test_milestones_reached_on_fund(self, client, auth_header):
        r = client.post("/savings/goals", json={"name": "M", "target_amount": 100}, headers=auth_header)
        goal_id = r.get_json()["id"]
        client.put(f"/savings/goals/{goal_id}", json={"add_funds": 50}, headers=auth_header)
        r = client.get(f"/savings/goals/{goal_id}/milestones", headers=auth_header)
        ms = r.get_json()
        reached = [m for m in ms if m["reached_at"] is not None]
        assert len(reached) == 2  # 25% (25) and 50% (50)

    def test_milestones_all_reached(self, client, auth_header):
        r = client.post("/savings/goals", json={"name": "M", "target_amount": 100}, headers=auth_header)
        goal_id = r.get_json()["id"]
        client.put(f"/savings/goals/{goal_id}", json={"current_amount": 100}, headers=auth_header)
        r = client.get(f"/savings/goals/{goal_id}/milestones", headers=auth_header)
        ms = r.get_json()
        assert all(m["reached_at"] is not None for m in ms)

    def test_milestones_not_found(self, client, auth_header):
        r = client.get("/savings/goals/9999/milestones", headers=auth_header)
        assert r.status_code == 404

    def test_milestones_recreated_on_target_change(self, client, auth_header):
        r = client.post("/savings/goals", json={"name": "M", "target_amount": 100}, headers=auth_header)
        goal_id = r.get_json()["id"]
        client.put(f"/savings/goals/{goal_id}", json={"target_amount": 200}, headers=auth_header)
        r = client.get(f"/savings/goals/{goal_id}/milestones", headers=auth_header)
        ms = r.get_json()
        amounts = [m["amount"] for m in ms]
        assert amounts == [50.0, 100.0, 150.0, 200.0]

    def test_create_goal_with_initial_amount_milestones(self, client, auth_header):
        r = client.post(
            "/savings/goals",
            json={"name": "M", "target_amount": 100, "current_amount": 75},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]
        r = client.get(f"/savings/goals/{goal_id}/milestones", headers=auth_header)
        ms = r.get_json()
        reached = [m for m in ms if m["reached_at"] is not None]
        assert len(reached) == 3  # 25, 50, 75

    def test_unauthenticated(self, client):
        r = client.get("/savings/goals")
        assert r.status_code == 401
