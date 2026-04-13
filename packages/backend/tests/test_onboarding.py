def test_onboarding_requires_auth(client):
    r = client.get("/onboarding/status")
    assert r.status_code in (401, 422)

    r = client.post("/onboarding/complete-step", json={"step": "has_expense"})
    assert r.status_code in (401, 422)

    r = client.get("/onboarding/suggestions")
    assert r.status_code in (401, 422)


def test_status_empty(client, auth_header):
    r = client.get("/onboarding/status", headers=auth_header)
    assert r.status_code == 200
    status = r.get_json()
    assert status["has_expense"] is False
    assert status["has_category"] is False
    assert status["has_bill"] is False
    assert status["has_budget_goal"] is False
    assert status["profile_complete"] is False


def test_complete_step(client, auth_header):
    r = client.post(
        "/onboarding/complete-step",
        json={"step": "has_budget_goal"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["completed"] is True

    r = client.get("/onboarding/status", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["has_budget_goal"] is True

    # Repeating should not error
    r = client.post(
        "/onboarding/complete-step",
        json={"step": "has_budget_goal"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["already_completed"] is True


def test_suggestions(client, auth_header):
    r = client.get("/onboarding/suggestions", headers=auth_header)
    assert r.status_code == 200
    suggestions = r.get_json()
    assert len(suggestions) == 5
    steps = [s["step"] for s in suggestions]
    assert "has_expense" in steps
    assert "has_budget_goal" in steps

    # Complete a step and check suggestions shrink
    client.post(
        "/onboarding/complete-step",
        json={"step": "profile_complete"},
        headers=auth_header,
    )
    r = client.get("/onboarding/suggestions", headers=auth_header)
    assert r.status_code == 200
    suggestions = r.get_json()
    assert len(suggestions) == 4
    assert "profile_complete" not in [s["step"] for s in suggestions]
