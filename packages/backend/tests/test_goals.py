import pytest
from app.models import Goal, GoalMilestone, db

def test_get_goals_empty(client, auth_headers):
    response = client.get("/goals", headers=auth_headers)
    assert response.status_code == 200
    assert response.json == []

def test_create_goal(client, auth_headers):
    data = {
        "name": "Buy a car",
        "target_amount": 10000.0,
        "deadline": "2026-12-31",
        "milestones": [
            {"name": "Save 5k", "target_amount": 5000.0}
        ]
    }
    response = client.post("/goals", json=data, headers=auth_headers)
    assert response.status_code == 201

    res2 = client.get("/goals", headers=auth_headers)
    assert len(res2.json) == 1
    assert res2.json[0]["name"] == "Buy a car"
    assert len(res2.json[0]["milestones"]) == 1
