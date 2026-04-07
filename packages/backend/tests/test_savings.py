import pytest


@pytest.fixture
def sample_goal(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={
            "name": "Emergency Fund",
            "description": "6 months expenses",
            "target_amount": 50000,
            "currency": "INR",
            "target_date": "2026-12-31",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()["id"]


class TestSavingsGoals:
    def test_create_goal(self, client, auth_header):
        r = client.post(
            "/savings-goals",
            json={
                "name": "Vacation Fund",
                "description": "Japan trip 2026",
                "target_amount": 2000,
                "currency": "USD",
                "target_date": "2026-06-01",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        assert "id" in r.get_json()

    def test_create_goal_default_currency(self, client, auth_header):
        r = client.post(
            "/savings-goals",
            json={
                "name": "Test Goal",
                "target_amount": 1000,
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    def test_list_goals(self, client, auth_header, sample_goal):
        r = client.get("/savings-goals", headers=auth_header)
        assert r.status_code == 200
        goals = r.get_json()
        assert isinstance(goals, list)
        assert len(goals) >= 1
        assert goals[0]["name"] == "Emergency Fund"

    def test_get_goal(self, client, auth_header, sample_goal):
        r = client.get(f"/savings-goals/{sample_goal}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["name"] == "Emergency Fund"
        assert data["target_amount"] == 50000.0
        assert data["current_amount"] == 0.0
        assert data["progress_pct"] == 0.0

    def test_get_goal_not_found(self, client, auth_header):
        r = client.get("/savings-goals/99999", headers=auth_header)
        assert r.status_code == 404

    def test_update_goal(self, client, auth_header, sample_goal):
        r = client.put(
            f"/savings-goals/{sample_goal}",
            json={"name": "Updated Goal Name", "target_amount": 60000},
            headers=auth_header,
        )
        assert r.status_code == 200
        r2 = client.get(f"/savings-goals/{sample_goal}", headers=auth_header)
        data = r2.get_json()
        assert data["name"] == "Updated Goal Name"
        assert data["target_amount"] == 60000.0

    def test_delete_goal(self, client, auth_header, sample_goal):
        r = client.delete(f"/savings-goals/{sample_goal}", headers=auth_header)
        assert r.status_code == 200
        r2 = client.get(f"/savings-goals/{sample_goal}", headers=auth_header)
        assert r2.status_code == 404

    def test_contribute(self, client, auth_header, sample_goal):
        r = client.post(
            f"/savings-goals/{sample_goal}/contribute",
            json={"amount": 5000},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["current_amount"] == 5000.0
        assert data["progress_pct"] == 10.0

    def test_contribute_negative_fails(self, client, auth_header, sample_goal):
        r = client.post(
            f"/savings-goals/{sample_goal}/contribute",
            json={"amount": -100},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_contribute_multiple_and_milestone_auto(self, client, auth_header, auth_header2):
        # Create a goal with milestones
        r = client.post(
            "/savings-goals",
            json={
                "name": "Car Fund",
                "target_amount": 10000,
                "currency": "USD",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        goal_id = r.get_json()["id"]

        # Add a milestone at 50%
        r = client.post(
            f"/savings-goals/{goal_id}/milestones",
            json={"name": "50% reached", "target_amount": 5000},
            headers=auth_header,
        )
        assert r.status_code == 201
        milestone_id = r.get_json()["id"]

        # Contribute 3000 - milestone not yet reached
        r = client.post(
            f"/savings-goals/{goal_id}/contribute",
            json={"amount": 3000},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["progress_pct"] == 30.0

        # Contribute 2500 more - now 5500 total, milestone reached
        r = client.post(
            f"/savings-goals/{goal_id}/contribute",
            json={"amount": 2500},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["current_amount"] == 5500.0

        # Check milestone was auto-achieved
        r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
        data = r.get_json()
        milestones = data["milestones"]
        assert len(milestones) == 1
        assert milestones[0]["achieved"] is True
        assert milestones[0]["achieved_at"] is not None

    def test_milestone_crud(self, client, auth_header, sample_goal):
        # Create milestone
        r = client.post(
            f"/savings-goals/{sample_goal}/milestones",
            json={"name": "First $1k", "target_amount": 1000},
            headers=auth_header,
        )
        assert r.status_code == 201
        mid = r.get_json()["id"]

        # Update milestone
        r = client.put(
            f"/savings-goals/{sample_goal}/milestones/{mid}",
            json={"name": "Updated Milestone", "target_amount": 2000},
            headers=auth_header,
        )
        assert r.status_code == 200

        # Delete milestone
        r = client.delete(f"/savings-goals/{sample_goal}/milestones/{mid}", headers=auth_header)
        assert r.status_code == 200

    def test_goal_requires_auth(self, client):
        r = client.get("/savings-goals")
        assert r.status_code == 401

    def test_cannot_access_other_user_goal(self, client, auth_header, auth_header2, sample_goal):
        # auth_header2 is a different user - can't access sample_goal
        r = client.get(f"/savings-goals/{sample_goal}", headers=auth_header2)
        assert r.status_code == 404


@pytest.fixture
def auth_header2(client):
    email = "test2@example.com"
    password = "password123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}
