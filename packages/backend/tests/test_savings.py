"""Tests for goal-based savings tracking & milestones."""


def _register(client, email, password="secret123"):
    client.post("/auth/register", json={"email": email, "password": password})


def _login(client, email, password="secret123"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.get_json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestSavingsGoalCRUD:
    def test_create_goal(self, client):
        _register(client, "saver@test.com")
        token = _login(client, "saver@test.com")
        r = client.post(
            "/savings",
            json={"name": "Vacation", "target_amount": 5000, "deadline": "2026-12-31"},
            headers=_auth(token),
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Vacation"
        assert float(data["target_amount"]) == 5000
        assert data["progress_pct"] == 0
        assert data["completed"] is False

    def test_create_goal_requires_name(self, client):
        _register(client, "noname@test.com")
        token = _login(client, "noname@test.com")
        r = client.post("/savings", json={"target_amount": 100}, headers=_auth(token))
        assert r.status_code == 400

    def test_list_goals(self, client):
        _register(client, "list@test.com")
        token = _login(client, "list@test.com")
        client.post("/savings", json={"name": "A", "target_amount": 100}, headers=_auth(token))
        client.post("/savings", json={"name": "B", "target_amount": 200}, headers=_auth(token))
        r = client.get("/savings", headers=_auth(token))
        assert r.status_code == 200
        assert len(r.get_json()["goals"]) == 2

    def test_get_goal_with_milestones(self, client):
        _register(client, "detail@test.com")
        token = _login(client, "detail@test.com")
        r = client.post("/savings", json={"name": "Car", "target_amount": 10000}, headers=_auth(token))
        gid = r.get_json()["id"]
        r = client.get(f"/savings/{gid}", headers=_auth(token))
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["milestones"]) == 4  # 25%, 50%, 75%, 100%
        assert data["milestones"][0]["target_pct"] == 25

    def test_update_goal(self, client):
        _register(client, "upd@test.com")
        token = _login(client, "upd@test.com")
        r = client.post("/savings", json={"name": "Old", "target_amount": 100}, headers=_auth(token))
        gid = r.get_json()["id"]
        r = client.patch(f"/savings/{gid}", json={"name": "New"}, headers=_auth(token))
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"

    def test_delete_goal(self, client):
        _register(client, "del@test.com")
        token = _login(client, "del@test.com")
        r = client.post("/savings", json={"name": "Temp", "target_amount": 50}, headers=_auth(token))
        gid = r.get_json()["id"]
        r = client.delete(f"/savings/{gid}", headers=_auth(token))
        assert r.status_code == 200
        r = client.get(f"/savings/{gid}", headers=_auth(token))
        assert r.status_code == 404


class TestContributions:
    def test_contribute_to_goal(self, client):
        _register(client, "cont@test.com")
        token = _login(client, "cont@test.com")
        r = client.post("/savings", json={"name": "Fund", "target_amount": 1000}, headers=_auth(token))
        gid = r.get_json()["id"]
        r = client.post(
            f"/savings/{gid}/contribute",
            json={"amount": 250, "notes": "First deposit"},
            headers=_auth(token),
        )
        assert r.status_code == 201
        data = r.get_json()
        assert float(data["new_total"]) == 250
        assert data["progress_pct"] == 25.0

    def test_milestone_reached_on_contribution(self, client):
        _register(client, "mile@test.com")
        token = _login(client, "mile@test.com")
        r = client.post("/savings", json={"name": "Goal", "target_amount": 100}, headers=_auth(token))
        gid = r.get_json()["id"]
        # Contribute 50 — should hit 25% and 50% milestones
        r = client.post(
            f"/savings/{gid}/contribute",
            json={"amount": 50},
            headers=_auth(token),
        )
        data = r.get_json()
        assert data["progress_pct"] == 50.0
        reached = data.get("milestones_reached", [])
        reached_pcts = [m["target_pct"] for m in reached]
        assert 25 in reached_pcts
        assert 50 in reached_pcts

    def test_goal_completes_at_100(self, client):
        _register(client, "complete@test.com")
        token = _login(client, "complete@test.com")
        r = client.post("/savings", json={"name": "Done", "target_amount": 100}, headers=_auth(token))
        gid = r.get_json()["id"]
        r = client.post(f"/savings/{gid}/contribute", json={"amount": 100}, headers=_auth(token))
        data = r.get_json()
        assert data["completed"] is True
        assert data["progress_pct"] == 100.0

    def test_cannot_contribute_to_completed_goal(self, client):
        _register(client, "done@test.com")
        token = _login(client, "done@test.com")
        r = client.post("/savings", json={"name": "Done", "target_amount": 50}, headers=_auth(token))
        gid = r.get_json()["id"]
        client.post(f"/savings/{gid}/contribute", json={"amount": 50}, headers=_auth(token))
        r = client.post(f"/savings/{gid}/contribute", json={"amount": 10}, headers=_auth(token))
        assert r.status_code == 400


class TestFilters:
    def test_filter_active_goals(self, client):
        _register(client, "filter@test.com")
        token = _login(client, "filter@test.com")
        r = client.post("/savings", json={"name": "Active", "target_amount": 1000}, headers=_auth(token))
        r2 = client.post("/savings", json={"name": "Finish", "target_amount": 10}, headers=_auth(token))
        gid = r2.get_json()["id"]
        client.post(f"/savings/{gid}/contribute", json={"amount": 10}, headers=_auth(token))
        r = client.get("/savings?status=active", headers=_auth(token))
        names = [g["name"] for g in r.get_json()["goals"]]
        assert "Active" in names
        assert "Finish" not in names
