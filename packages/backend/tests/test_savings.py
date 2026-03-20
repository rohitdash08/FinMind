from datetime import date


def test_savings_goals_crud(client, auth_header):
    # Initially empty
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        "name": "Emergency Fund",
        "target_amount": 5000.00,
        "currency": "USD",
        "target_date": "2026-12-31",
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # List has 1
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == goal_id
    assert items[0]["name"] == "Emergency Fund"
    assert items[0]["target_amount"] == 5000.00
    assert items[0]["current_amount"] == 0
    assert items[0]["progress_pct"] == 0
    assert items[0]["achieved"] is False

    # Get detail
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["name"] == "Emergency Fund"
    assert detail["contributions"] == []

    # Update
    r = client.put(
        f"/savings/{goal_id}",
        json={"name": "Rainy Day Fund", "target_amount": 3000.00},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Rainy Day Fund"
    assert r.get_json()["target_amount"] == 3000.00

    # Delete
    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # List empty again
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_contributions(client, auth_header):
    # Create goal
    r = client.post(
        "/savings",
        json={"name": "Vacation", "target_amount": 1000.00, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Contribute
    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 250.00, "notes": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["current_amount"] == 250.00
    assert body["achieved"] is False

    # Second contribution
    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 300.00},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["current_amount"] == 550.00

    # List contributions
    r = client.get(f"/savings/{goal_id}/contributions", headers=auth_header)
    assert r.status_code == 200
    contribs = r.get_json()
    assert len(contribs) == 2

    # Check progress on goal
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["current_amount"] == 550.00
    assert detail["progress_pct"] == 55.0
    assert len(detail["contributions"]) == 2


def test_savings_milestone_achievement(client, auth_header):
    # Create goal with small target
    r = client.post(
        "/savings",
        json={"name": "Coffee Machine", "target_amount": 100.00, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Contribute exact amount
    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 100.00},
        headers=auth_header,
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["achieved"] is True
    assert body["current_amount"] == 100.00

    # Verify goal shows achieved
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["achieved"] is True
    assert r.get_json()["progress_pct"] == 100.0


def test_savings_over_contribution(client, auth_header):
    # Create goal and over-contribute
    r = client.post(
        "/savings",
        json={"name": "Gift", "target_amount": 50.00, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 75.00},
        headers=auth_header,
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["achieved"] is True
    assert body["current_amount"] == 75.00


def test_savings_not_found(client, auth_header):
    r = client.get("/savings/9999", headers=auth_header)
    assert r.status_code == 404

    r = client.put("/savings/9999", json={"name": "x"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/savings/9999", headers=auth_header)
    assert r.status_code == 404

    r = client.post("/savings/9999/contribute", json={"amount": 10}, headers=auth_header)
    assert r.status_code == 404

    r = client.get("/savings/9999/contributions", headers=auth_header)
    assert r.status_code == 404


def test_savings_auth_required(client):
    # No auth header — should get 401
    r = client.get("/savings")
    assert r.status_code == 401

    r = client.post("/savings", json={"name": "x", "target_amount": 100})
    assert r.status_code == 401

    r = client.get("/savings/1")
    assert r.status_code == 401

    r = client.put("/savings/1", json={"name": "x"})
    assert r.status_code == 401

    r = client.delete("/savings/1")
    assert r.status_code == 401

    r = client.post("/savings/1/contribute", json={"amount": 10})
    assert r.status_code == 401

    r = client.get("/savings/1/contributions")
    assert r.status_code == 401


def test_savings_defaults_to_user_preferred_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "INR"}, headers=auth_header
    )
    assert r.status_code == 200

    payload = {
        "name": "Bike Fund",
        "target_amount": 2000.00,
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["currency"] == "INR"
