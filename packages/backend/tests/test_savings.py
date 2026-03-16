"""
Tests for Goal-based savings tracking & milestones (Issue #133).

Covers:
- CRUD for savings goals
- Deposit / withdrawal updating current_amount
- Goal achievement detection
- Milestone CRUD
- Milestone auto-achievement on deposit
- Progress percentage calculation
- Input validation
- Authentication requirements
"""

from __future__ import annotations

import pytest
from app.extensions import db
from app.models import SavingsGoal, SavingsMilestone


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="savings@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _create_goal(client, headers, **kwargs):
    payload = {"name": "Emergency Fund", "target_amount": 10000, "currency": "INR", **kwargs}
    return client.post("/savings/goals", json=payload, headers=headers)


# ─────────────────────────────────────────────────────────────────────────────
# Goal CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TestSavingsGoalCrud:
    def test_create_goal(self, client, app_fixture):
        h = _auth(client)
        r = _create_goal(client, h)
        assert r.status_code == 201
        d = r.get_json()
        assert d["name"] == "Emergency Fund"
        assert d["target_amount"] == 10000.0
        assert d["current_amount"] == 0.0
        assert d["achieved"] is False
        assert d["progress_percent"] == 0.0

    def test_create_goal_missing_name(self, client, app_fixture):
        h = _auth(client)
        r = client.post("/savings/goals", json={"target_amount": 1000}, headers=h)
        assert r.status_code == 400
        assert "name" in r.get_json()["error"]

    def test_create_goal_invalid_target(self, client, app_fixture):
        h = _auth(client)
        r = client.post("/savings/goals", json={"name": "X", "target_amount": -100}, headers=h)
        assert r.status_code == 400

    def test_list_goals_empty(self, client, app_fixture):
        h = _auth(client, "list_empty@test.com")
        r = client.get("/savings/goals", headers=h)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_goals_returns_own_only(self, client, app_fixture):
        h1 = _auth(client, "user1@test.com")
        h2 = _auth(client, "user2@test.com")
        _create_goal(client, h1, name="Goal A")
        _create_goal(client, h2, name="Goal B")

        r = client.get("/savings/goals", headers=h1)
        goals = r.get_json()
        assert all(g["name"] == "Goal A" for g in goals)
        assert len(goals) == 1

    def test_get_goal(self, client, app_fixture):
        h = _auth(client)
        goal_id = _create_goal(client, h).get_json()["id"]
        r = client.get(f"/savings/goals/{goal_id}", headers=h)
        assert r.status_code == 200
        assert r.get_json()["id"] == goal_id
        assert "milestones" in r.get_json()

    def test_get_goal_not_found(self, client, app_fixture):
        h = _auth(client)
        r = client.get("/savings/goals/99999", headers=h)
        assert r.status_code == 404

    def test_get_goal_other_user_forbidden(self, client, app_fixture):
        h1 = _auth(client, "owner@test.com")
        h2 = _auth(client, "other@test.com")
        goal_id = _create_goal(client, h1).get_json()["id"]
        r = client.get(f"/savings/goals/{goal_id}", headers=h2)
        assert r.status_code == 404

    def test_update_goal(self, client, app_fixture):
        h = _auth(client)
        goal_id = _create_goal(client, h).get_json()["id"]
        r = client.patch(f"/savings/goals/{goal_id}", json={"name": "Updated", "target_amount": 20000}, headers=h)
        assert r.status_code == 200
        assert r.get_json()["name"] == "Updated"
        assert r.get_json()["target_amount"] == 20000.0

    def test_update_goal_empty_name_rejected(self, client, app_fixture):
        h = _auth(client)
        goal_id = _create_goal(client, h).get_json()["id"]
        r = client.patch(f"/savings/goals/{goal_id}", json={"name": ""}, headers=h)
        assert r.status_code == 400

    def test_delete_goal(self, client, app_fixture):
        h = _auth(client)
        goal_id = _create_goal(client, h).get_json()["id"]
        r = client.delete(f"/savings/goals/{goal_id}", headers=h)
        assert r.status_code == 200
        assert client.get(f"/savings/goals/{goal_id}", headers=h).status_code == 404

    def test_goals_require_auth(self, client, app_fixture):
        assert client.get("/savings/goals").status_code == 401
        assert client.post("/savings/goals", json={}).status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Deposits & achievement
# ─────────────────────────────────────────────────────────────────────────────

class TestDeposits:
    def test_deposit_increases_amount(self, client, app_fixture):
        h = _auth(client, "dep@test.com")
        goal_id = _create_goal(client, h, target_amount=1000).get_json()["id"]
        r = client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": 300}, headers=h)
        assert r.status_code == 200
        assert r.get_json()["current_amount"] == 300.0
        assert r.get_json()["progress_percent"] == 30.0

    def test_withdrawal_decreases_amount(self, client, app_fixture):
        h = _auth(client, "wd@test.com")
        goal_id = _create_goal(client, h, target_amount=1000).get_json()["id"]
        client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": 500}, headers=h)
        r = client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": -200}, headers=h)
        assert r.get_json()["current_amount"] == 300.0

    def test_withdrawal_cannot_go_below_zero(self, client, app_fixture):
        h = _auth(client, "zero@test.com")
        goal_id = _create_goal(client, h, target_amount=1000).get_json()["id"]
        r = client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": -999999}, headers=h)
        assert r.get_json()["current_amount"] == 0.0

    def test_goal_achieved_on_full_deposit(self, client, app_fixture):
        h = _auth(client, "achieve@test.com")
        goal_id = _create_goal(client, h, target_amount=1000).get_json()["id"]
        r = client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": 1000}, headers=h)
        d = r.get_json()
        assert d["achieved"] is True
        assert d["newly_achieved"] is True

    def test_goal_not_achieved_if_partial(self, client, app_fixture):
        h = _auth(client, "partial@test.com")
        goal_id = _create_goal(client, h, target_amount=1000).get_json()["id"]
        r = client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": 999}, headers=h)
        assert r.get_json()["achieved"] is False

    def test_deposit_missing_amount(self, client, app_fixture):
        h = _auth(client, "noamt@test.com")
        goal_id = _create_goal(client, h).get_json()["id"]
        r = client.post(f"/savings/goals/{goal_id}/deposit", json={}, headers=h)
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Milestones
# ─────────────────────────────────────────────────────────────────────────────

class TestMilestones:
    def _setup(self, client, email="ms@test.com"):
        h = _auth(client, email)
        goal_id = _create_goal(client, h, target_amount=10000).get_json()["id"]
        return h, goal_id

    def test_create_milestone(self, client, app_fixture):
        h, gid = self._setup(client, "ms1@test.com")
        r = client.post(f"/savings/goals/{gid}/milestones",
                        json={"name": "25%", "target_amount": 2500}, headers=h)
        assert r.status_code == 201
        d = r.get_json()
        assert d["name"] == "25%"
        assert d["achieved"] is False

    def test_milestone_exceeding_goal_rejected(self, client, app_fixture):
        h, gid = self._setup(client, "ms2@test.com")
        r = client.post(f"/savings/goals/{gid}/milestones",
                        json={"name": "Over", "target_amount": 99999}, headers=h)
        assert r.status_code == 400
        assert "exceed" in r.get_json()["error"]

    def test_milestone_auto_achieved_if_current_exceeds(self, client, app_fixture):
        h, gid = self._setup(client, "ms3@test.com")
        # Deposit 5000 first
        client.post(f"/savings/goals/{gid}/deposit", json={"amount": 5000}, headers=h)
        # Add milestone below current
        r = client.post(f"/savings/goals/{gid}/milestones",
                        json={"name": "25%", "target_amount": 2500}, headers=h)
        assert r.get_json()["achieved"] is True

    def test_milestone_achieved_on_deposit(self, client, app_fixture):
        h, gid = self._setup(client, "ms4@test.com")
        client.post(f"/savings/goals/{gid}/milestones",
                    json={"name": "Half", "target_amount": 5000}, headers=h)
        r = client.post(f"/savings/goals/{gid}/deposit", json={"amount": 5000}, headers=h)
        d = r.get_json()
        assert "Half" in d["newly_achieved_milestones"]

    def test_list_milestones(self, client, app_fixture):
        h, gid = self._setup(client, "ms5@test.com")
        client.post(f"/savings/goals/{gid}/milestones", json={"name": "A", "target_amount": 1000}, headers=h)
        client.post(f"/savings/goals/{gid}/milestones", json={"name": "B", "target_amount": 5000}, headers=h)
        r = client.get(f"/savings/goals/{gid}/milestones", headers=h)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_delete_milestone(self, client, app_fixture):
        h, gid = self._setup(client, "ms6@test.com")
        mid = client.post(f"/savings/goals/{gid}/milestones",
                          json={"name": "X", "target_amount": 1000}, headers=h).get_json()["id"]
        r = client.delete(f"/savings/goals/{gid}/milestones/{mid}", headers=h)
        assert r.status_code == 200
        assert len(client.get(f"/savings/goals/{gid}/milestones", headers=h).get_json()) == 0

    def test_update_milestone(self, client, app_fixture):
        h, gid = self._setup(client, "ms7@test.com")
        mid = client.post(f"/savings/goals/{gid}/milestones",
                          json={"name": "Old", "target_amount": 1000}, headers=h).get_json()["id"]
        r = client.patch(f"/savings/goals/{gid}/milestones/{mid}", json={"name": "New"}, headers=h)
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"

    def test_milestone_goal_detail_includes_milestones(self, client, app_fixture):
        h, gid = self._setup(client, "ms8@test.com")
        client.post(f"/savings/goals/{gid}/milestones", json={"name": "M1", "target_amount": 1000}, headers=h)
        r = client.get(f"/savings/goals/{gid}", headers=h)
        assert len(r.get_json()["milestones"]) == 1

    def test_withdrawal_below_milestone_resets_achieved(self, client, app_fixture):
        """A withdrawal that drops current_amount below a milestone threshold
        must reset milestone.achieved back to False."""
        h, gid = self._setup(client, "ms_rev@test.com")
        # Add milestone at 3000
        mid = client.post(
            f"/savings/goals/{gid}/milestones",
            json={"name": "3k mark", "target_amount": 3000},
            headers=h,
        ).get_json()["id"]

        # Deposit 5000 → milestone achieved
        client.post(f"/savings/goals/{gid}/deposit", json={"amount": 5000}, headers=h)
        ms = client.get(f"/savings/goals/{gid}/milestones", headers=h).get_json()
        assert next(m for m in ms if m["id"] == mid)["achieved"] is True

        # Withdraw 3000 → current_amount = 2000 < milestone threshold
        client.post(f"/savings/goals/{gid}/deposit", json={"amount": -3000}, headers=h)
        ms_after = client.get(f"/savings/goals/{gid}/milestones", headers=h).get_json()
        assert next(m for m in ms_after if m["id"] == mid)["achieved"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Regression / edge-case tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDepositEdgeCases:
    def test_withdrawal_below_target_resets_goal_achieved(self, client, app_fixture):
        """After a goal is marked achieved, a withdrawal that drops current_amount
        below target_amount must set goal.achieved back to False."""
        h = _auth(client, "rev_goal@test.com")
        goal_id = _create_goal(client, h, target_amount=1000).get_json()["id"]

        # Reach target → achieved=True
        r = client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": 1000}, headers=h)
        assert r.get_json()["achieved"] is True

        # Withdraw 500 → current=500 < target=1000 → achieved must flip to False
        r = client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": -500}, headers=h)
        d = r.get_json()
        assert r.status_code == 200
        assert d["current_amount"] == 500.0
        assert d["achieved"] is False

    def test_deposit_zero_returns_400(self, client, app_fixture):
        """A deposit with amount=0 must be rejected with 400 Bad Request."""
        h = _auth(client, "zero_dep@test.com")
        goal_id = _create_goal(client, h, target_amount=1000).get_json()["id"]

        r = client.post(f"/savings/goals/{goal_id}/deposit", json={"amount": 0}, headers=h)
        assert r.status_code == 400
        assert "non-zero" in r.get_json()["error"]
