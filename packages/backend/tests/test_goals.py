"""Tests for savings goals feature."""

from datetime import date, timedelta


class TestGoalsCRUD:
    def test_create_goal(self, client, auth_header):
        r = client.post(
            "/goals/",
            json={
                "name": "Emergency Fund",
                "target_amount": 10000,
                "currency": "USD",
                "deadline": "2026-12-31",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Emergency Fund"
        assert data["target_amount"] == 10000
        assert data["current_amount"] == 0
        assert data["status"] == "ACTIVE"

    def test_create_goal_missing_fields(self, client, auth_header):
        r = client.post("/goals/", json={"name": "Test"}, headers=auth_header)
        assert r.status_code == 400

    def test_create_goal_invalid_amount(self, client, auth_header):
        r = client.post(
            "/goals/", json={"name": "Test", "target_amount": -100}, headers=auth_header
        )
        assert r.status_code == 400

    def test_list_goals(self, client, auth_header):
        client.post(
            "/goals/",
            json={"name": "Goal 1", "target_amount": 1000},
            headers=auth_header,
        )
        client.post(
            "/goals/",
            json={"name": "Goal 2", "target_amount": 2000},
            headers=auth_header,
        )

        r = client.get("/goals/", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_get_goal(self, client, auth_header):
        r = client.post(
            "/goals/",
            json={"name": "Vacation", "target_amount": 5000},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]

        r = client.get(f"/goals/{goal_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["name"] == "Vacation"

    def test_get_nonexistent_goal(self, client, auth_header):
        r = client.get("/goals/999", headers=auth_header)
        assert r.status_code == 404

    def test_update_goal(self, client, auth_header):
        r = client.post(
            "/goals/",
            json={"name": "Old Name", "target_amount": 1000},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]

        r = client.put(
            f"/goals/{goal_id}",
            json={"name": "New Name", "target_amount": 2000},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["name"] == "New Name"

    def test_cancel_goal(self, client, auth_header):
        r = client.post(
            "/goals/",
            json={"name": "Cancel Me", "target_amount": 500},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]

        r = client.delete(f"/goals/{goal_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["status"] == "CANCELLED"


class TestContributions:
    def test_add_contribution(self, client, auth_header):
        r = client.post(
            "/goals/", json={"name": "Fund", "target_amount": 1000}, headers=auth_header
        )
        goal_id = r.get_json()["id"]

        r = client.post(
            f"/goals/{goal_id}/contribute",
            json={"amount": 250, "note": "First deposit"},
            headers=auth_header,
        )
        assert r.status_code == 201
        assert r.get_json()["amount"] == 250

    def test_contribution_invalid_amount(self, client, auth_header):
        r = client.post(
            "/goals/", json={"name": "Fund", "target_amount": 1000}, headers=auth_header
        )
        goal_id = r.get_json()["id"]

        r = client.post(
            f"/goals/{goal_id}/contribute", json={"amount": -50}, headers=auth_header
        )
        assert r.status_code == 400

    def test_auto_complete_on_target(self, client, auth_header):
        r = client.post(
            "/goals/",
            json={"name": "Quick Goal", "target_amount": 100},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]

        client.post(
            f"/goals/{goal_id}/contribute", json={"amount": 100}, headers=auth_header
        )

        r = client.get(f"/goals/{goal_id}", headers=auth_header)
        assert r.get_json()["status"] == "COMPLETED"

    def test_list_contributions(self, client, auth_header):
        r = client.post(
            "/goals/", json={"name": "Fund", "target_amount": 1000}, headers=auth_header
        )
        goal_id = r.get_json()["id"]

        client.post(
            f"/goals/{goal_id}/contribute", json={"amount": 100}, headers=auth_header
        )
        client.post(
            f"/goals/{goal_id}/contribute", json={"amount": 200}, headers=auth_header
        )

        r = client.get(f"/goals/{goal_id}/contributions", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_contribute_to_cancelled_goal(self, client, auth_header):
        r = client.post(
            "/goals/",
            json={"name": "Dead Goal", "target_amount": 500},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]
        client.delete(f"/goals/{goal_id}", headers=auth_header)

        r = client.post(
            f"/goals/{goal_id}/contribute", json={"amount": 50}, headers=auth_header
        )
        assert r.status_code == 400


class TestProgress:
    def test_progress_endpoint(self, client, auth_header):
        r = client.post(
            "/goals/",
            json={
                "name": "House",
                "target_amount": 50000,
                "deadline": (date.today() + timedelta(days=365)).isoformat(),
            },
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]

        client.post(
            f"/goals/{goal_id}/contribute", json={"amount": 12500}, headers=auth_header
        )

        r = client.get(f"/goals/{goal_id}/progress", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["progress_pct"] == 25.0
        assert data["remaining"] == 37500.0
        assert "milestones" in data
        assert data["milestones"][0]["reached"]  # 25% reached
        assert not data["milestones"][1]["reached"]  # 50% not yet
        assert "daily_savings_needed" in data
        assert data["on_track"]

    def test_progress_nonexistent(self, client, auth_header):
        r = client.get("/goals/999/progress", headers=auth_header)
        assert r.status_code == 404
