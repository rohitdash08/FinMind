"""Tests for savings goals CRUD endpoints."""


def _create_goal(client, auth_header, name="Emergency Fund", target=1000):
    r = client.post(
        "/savings/goals",
        json={"name": name, "target_amount": target, "currency": "INR"},
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()


# 1. Auth required
def test_savings_requires_auth(client):
    r = client.get("/savings/goals")
    assert r.status_code in (401, 422)


# 2. Create goal with auto-milestones
def test_create_goal_with_milestones(client, auth_header):
    data = _create_goal(client, auth_header)
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 1000.0
    assert data["current_amount"] == 0.0
    assert data["progress"] == 0.0
    assert len(data["milestones"]) == 4
    pcts = [m["percentage"] for m in data["milestones"]]
    assert pcts == [25, 50, 75, 100]
    assert data["milestones"][0]["target_amount"] == 250.0
    assert data["milestones"][3]["target_amount"] == 1000.0


# 3. List goals
def test_list_goals(client, auth_header):
    _create_goal(client, auth_header, "Goal A", 500)
    _create_goal(client, auth_header, "Goal B", 1000)
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    goals = r.get_json()
    assert len(goals) >= 2


# 4. Update current_amount triggers milestone
def test_update_triggers_milestone(client, auth_header):
    goal = _create_goal(client, auth_header, "Vacation", 400)
    goal_id = goal["id"]
    r = client.patch(
        f"/savings/goals/{goal_id}",
        json={"current_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["progress"] == 25.0
    reached = [m for m in data["milestones"] if m["reached"]]
    assert len(reached) == 1
    assert reached[0]["percentage"] == 25


# 5. Delete goal removes milestones
def test_delete_goal(client, auth_header):
    goal = _create_goal(client, auth_header, "To Delete", 200)
    goal_id = goal["id"]
    r = client.delete(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 404


# 6. Invalid target_amount returns 400
def test_invalid_target_amount(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Bad", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400


# 7. Missing name returns 400
def test_missing_name(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "", "target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400


# 8. Get single goal
def test_get_single_goal(client, auth_header):
    goal = _create_goal(client, auth_header, "House Fund", 50000)
    r = client.get(f"/savings/goals/{goal['id']}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "House Fund"
    assert data["target_amount"] == 50000.0
