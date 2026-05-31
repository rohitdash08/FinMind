from datetime import datetime, timedelta


def test_insights_empty(client, auth_header):
    r = client.get("/reminders/optimization/insights", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "recommended_hour" in data
    assert "engagement_by_type" in data


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


def test_record_engagement(client, auth_header):
    r = client.post(
        "/reminders/optimization/record-engagement",
        json={"event_type": "opened", "channel": "email"},
        headers=auth_header,
    )
    assert r.status_code == 201


def test_performance_metrics_and_dashboard(client, auth_header):
    r = client.post(
        "/reminders/optimization/metrics",
        json={"metric_type": "open_rate", "metric_value": 0.85, "channel": "email"},
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/reminders/optimization/metrics",
        json={"metric_type": "click_rate", "metric_value": 0.42, "channel": "email"},
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/reminders/optimization/dashboard", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "last_7_days" in data
    assert "last_30_days" in data
