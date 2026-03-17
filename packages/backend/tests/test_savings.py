"""Tests for savings goals & milestones."""
from datetime import date, timedelta


def _goal_payload(**kwargs):
    base = {"name": "Emergency Fund", "target_amount": 10000}
    base.update(kwargs)
    return base


class TestSavingsGoalsCRUD:
    def test_create_goal_minimal(self, client, auth_header):
        r = client.post("/savings", json=_goal_payload(), headers=auth_header)
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Emergency Fund"
        assert data["target_amount"] == 10000.0
        assert data["current_amount"] == 0.0
        assert data["progress_pct"] == 0.0
        assert data["status"] == "ACTIVE"
        assert data["milestones_reached"] == []
        assert data["next_milestone_pct"] == 25

    def test_create_goal_with_all_fields(self, client, auth_header):
        deadline = (date.today() + timedelta(days=365)).isoformat()
        r = client.post(
            "/savings",
            json=_goal_payload(
                currency="USD",
                deadline=deadline,
                notes="For rainy days",
                initial_amount=500,
            ),
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["currency"] == "USD"
        assert data["deadline"] == deadline
        assert data["current_amount"] == 500.0

    def test_create_goal_missing_required_fields(self, client, auth_header):
        r = client.post("/savings", json={"name": "Test"}, headers=auth_header)
        assert r.status_code == 400

        r = client.post("/savings", json={"target_amount": 100}, headers=auth_header)
        assert r.status_code == 400

    def test_create_goal_invalid_target(self, client, auth_header):
        r = client.post("/savings", json=_goal_payload(target_amount=-100), headers=auth_header)
        assert r.status_code == 400

    def test_list_goals(self, client, auth_header):
        client.post("/savings", json=_goal_payload(name="Goal A"), headers=auth_header)
        client.post("/savings", json=_goal_payload(name="Goal B"), headers=auth_header)
        r = client.get("/savings", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_list_goals_filter_by_status(self, client, auth_header):
        r = client.post("/savings", json=_goal_payload(name="Active"), headers=auth_header)
        goal_id = r.get_json()["id"]
        client.patch(f"/savings/{goal_id}", json={"status": "PAUSED"}, headers=auth_header)

        client.post("/savings", json=_goal_payload(name="Also Active"), headers=auth_header)

        r = client.get("/savings?status=active", headers=auth_header)
        names = [g["name"] for g in r.get_json()]
        assert "Also Active" in names
        assert "Active" not in names

    def test_get_goal(self, client, auth_header):
        r = client.post("/savings", json=_goal_payload(), headers=auth_header)
        gid = r.get_json()["id"]
        r = client.get(f"/savings/{gid}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["id"] == gid

    def test_get_goal_not_found(self, client, auth_header):
        r = client.get("/savings/99999", headers=auth_header)
        assert r.status_code == 404

    def test_update_goal(self, client, auth_header):
        r = client.post("/savings", json=_goal_payload(), headers=auth_header)
        gid = r.get_json()["id"]
        r = client.patch(
            f"/savings/{gid}",
            json={"name": "Updated", "status": "PAUSED"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["name"] == "Updated"
        assert data["status"] == "PAUSED"

    def test_update_goal_invalid_status(self, client, auth_header):
        r = client.post("/savings", json=_goal_payload(), headers=auth_header)
        gid = r.get_json()["id"]
        r = client.patch(f"/savings/{gid}", json={"status": "BANANA"}, headers=auth_header)
        assert r.status_code == 400

    def test_delete_goal(self, client, auth_header):
        r = client.post("/savings", json=_goal_payload(), headers=auth_header)
        gid = r.get_json()["id"]
        r = client.delete(f"/savings/{gid}", headers=auth_header)
        assert r.status_code == 200
        assert client.get(f"/savings/{gid}", headers=auth_header).status_code == 404


class TestDepositsAndMilestones:
    def _create_goal(self, client, auth_header, target=1000):
        r = client.post("/savings", json=_goal_payload(target_amount=target), headers=auth_header)
        return r.get_json()["id"]

    def test_deposit_increases_current_amount(self, client, auth_header):
        gid = self._create_goal(client, auth_header)
        r = client.post(f"/savings/{gid}/deposits", json={"amount": 300}, headers=auth_header)
        assert r.status_code == 201
        data = r.get_json()
        assert data["current_amount"] == 300.0
        assert data["progress_pct"] == 30.0

    def test_deposit_invalid_amount(self, client, auth_header):
        gid = self._create_goal(client, auth_header)
        r = client.post(f"/savings/{gid}/deposits", json={"amount": -50}, headers=auth_header)
        assert r.status_code == 400

    def test_milestone_25_reached(self, client, auth_header):
        gid = self._create_goal(client, auth_header, target=1000)
        r = client.post(f"/savings/{gid}/deposits", json={"amount": 250}, headers=auth_header)
        data = r.get_json()
        assert 25 in data["milestones_reached"]
        assert data["next_milestone_pct"] == 50

    def test_milestone_50_reached(self, client, auth_header):
        gid = self._create_goal(client, auth_header, target=1000)
        client.post(f"/savings/{gid}/deposits", json={"amount": 500}, headers=auth_header)
        r = client.get(f"/savings/{gid}", headers=auth_header)
        data = r.get_json()
        assert 25 in data["milestones_reached"]
        assert 50 in data["milestones_reached"]
        assert data["next_milestone_pct"] == 75

    def test_goal_auto_completes_at_100_pct(self, client, auth_header):
        gid = self._create_goal(client, auth_header, target=500)
        r = client.post(f"/savings/{gid}/deposits", json={"amount": 500}, headers=auth_header)
        data = r.get_json()
        assert data["status"] == "COMPLETED"
        assert data["progress_pct"] == 100.0
        assert data["milestones_reached"] == [25, 50, 75, 100]

    def test_deposit_rejected_on_completed_goal(self, client, auth_header):
        gid = self._create_goal(client, auth_header, target=100)
        client.post(f"/savings/{gid}/deposits", json={"amount": 100}, headers=auth_header)
        r = client.post(f"/savings/{gid}/deposits", json={"amount": 50}, headers=auth_header)
        assert r.status_code == 400

    def test_list_deposits(self, client, auth_header):
        gid = self._create_goal(client, auth_header)
        client.post(f"/savings/{gid}/deposits", json={"amount": 100, "note": "paycheck"}, headers=auth_header)
        client.post(f"/savings/{gid}/deposits", json={"amount": 200}, headers=auth_header)
        r = client.get(f"/savings/{gid}/deposits", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_multiple_deposits_accumulate(self, client, auth_header):
        gid = self._create_goal(client, auth_header, target=1000)
        client.post(f"/savings/{gid}/deposits", json={"amount": 100}, headers=auth_header)
        client.post(f"/savings/{gid}/deposits", json={"amount": 150}, headers=auth_header)
        client.post(f"/savings/{gid}/deposits", json={"amount": 200}, headers=auth_header)
        r = client.get(f"/savings/{gid}", headers=auth_header)
        assert r.get_json()["current_amount"] == 450.0


class TestSavingsAuth:
    def test_all_endpoints_require_auth(self, client):
        assert client.get("/savings").status_code == 401
        assert client.post("/savings").status_code == 401
        assert client.get("/savings/1").status_code == 401
        assert client.patch("/savings/1").status_code == 401
        assert client.delete("/savings/1").status_code == 401
        assert client.post("/savings/1/deposits").status_code == 401
        assert client.get("/savings/1/deposits").status_code == 401

    def test_user_cannot_access_other_users_goal(self, client):
        # Register two users
        client.post("/auth/register", json={"email": "user1@test.com", "password": "pass1234"})
        r1 = client.post("/auth/login", json={"email": "user1@test.com", "password": "pass1234"})
        h1 = {"Authorization": f"Bearer {r1.get_json()['access_token']}"}

        client.post("/auth/register", json={"email": "user2@test.com", "password": "pass1234"})
        r2 = client.post("/auth/login", json={"email": "user2@test.com", "password": "pass1234"})
        h2 = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}

        r = client.post("/savings", json={"name": "Secret Goal", "target_amount": 5000}, headers=h1)
        gid = r.get_json()["id"]

        assert client.get(f"/savings/{gid}", headers=h2).status_code == 404
        assert client.patch(f"/savings/{gid}", json={"name": "Stolen"}, headers=h2).status_code == 404
        assert client.delete(f"/savings/{gid}", headers=h2).status_code == 404
