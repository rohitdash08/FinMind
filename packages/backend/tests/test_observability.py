def test_request_id_header_is_returned(client):
    response = client.get("/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert len(request_id) >= 16


def test_metrics_endpoint_exposes_http_and_reminder_metrics(client, auth_header):
    # Trigger baseline API traffic.
    health = client.get("/health")
    assert health.status_code == 200

    # Trigger reminder scheduling flow to populate product KPI counters.
    bill = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 59.0,
            "next_due_date": "2026-03-20",
            "cadence": "MONTHLY",
            "channel_email": True,
            "channel_whatsapp": False,
            "autopay_enabled": False,
        },
        headers=auth_header,
    )
    assert bill.status_code == 201
    bill_id = bill.get_json()["id"]

    scheduled = client.post(f"/reminders/bills/{bill_id}/schedule", headers=auth_header)
    assert scheduled.status_code == 200
    assert scheduled.get_json()["created"] >= 1

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    payload = metrics.get_data(as_text=True)
    assert "finmind_http_requests_total" in payload
    assert 'endpoint="/health"' in payload
    assert "finmind_reminder_events_total" in payload
    assert 'event="scheduled"' in payload
