from datetime import datetime, timedelta


def test_insights_empty(client, auth_header):
    r = client.get("/reminders/optimization/insights", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "recommended_hour" in data


def test_apply_optimization(client, auth_header):
    r = client.post(
        "/bills",
        json={
            "name": "Test Bill",
            "amount": 100,
            "next_due_date": (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    bill_id = r.get_json()["id"]

    r = client.post(f"/reminders/bills/{bill_id}/schedule", headers=auth_header)
    assert r.status_code == 200

    r = client.post("/reminders/optimization/apply", headers=auth_header)
    assert r.status_code == 200
    assert "updated" in r.get_json()


def test_ab_test_assign(client, auth_header):
    r = client.post("/reminders/optimization/ab-test/assign", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["variant"] in ["morning", "afternoon", "evening"]


def test_ab_test_results(client, auth_header):
    r = client.get("/reminders/optimization/ab-test/results", headers=auth_header)
    assert r.status_code == 200
