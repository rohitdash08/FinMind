from datetime import date, datetime, timedelta


def _create_bill(client, auth_header, *, due_date: str, autopay_enabled: bool = False):
    payload = {
        "name": "Electricity",
        "amount": 90.0,
        "next_due_date": due_date,
        "cadence": "MONTHLY",
        "channel_email": True,
        "channel_whatsapp": True,
        "autopay_enabled": autopay_enabled,
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def test_bill_reminders_schedule_supports_default_and_override_offsets(
    client, auth_header
):
    bill_id = _create_bill(client, auth_header, due_date="2026-03-20")

    # Hybrid default path: use system defaults [7, 3, 1]
    r = client.post(f"/reminders/bills/{bill_id}/schedule", headers=auth_header)
    assert r.status_code == 200
    created = r.get_json()["created"]
    # 3 offsets * 2 channels
    assert created == 6

    # Repeat should be deduped for same window.
    r = client.post(f"/reminders/bills/{bill_id}/schedule", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["created"] == 0

    # Override path: custom offsets should be used for a new bill.
    bill_id2 = _create_bill(client, auth_header, due_date="2026-03-25")
    r = client.post(
        f"/reminders/bills/{bill_id2}/schedule",
        json={"offsets_days": [5, 2]},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["created"] == 4


def test_autopay_generates_precheck_and_result_followup_for_both_channels(
    client, auth_header
):
    bill_id = _create_bill(
        client,
        auth_header,
        due_date=(date.today().replace(day=28)).isoformat(),
        autopay_enabled=True,
    )

    # Pre-check reminders should include an autopay check notice in both channels.
    r = client.post(f"/reminders/bills/{bill_id}/schedule", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/reminders", headers=auth_header)
    assert r.status_code == 200
    reminders = r.get_json()
    autopay_pre = [x for x in reminders if "Autopay check" in x["message"]]
    assert len(autopay_pre) == 2
    assert sorted([x["channel"] for x in autopay_pre]) == ["email", "whatsapp"]

    # Result follow-up should notify both channels.
    r = client.post(
        f"/reminders/bills/{bill_id}/autopay-result",
        json={"status": "SUCCESS"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["created"] == 2

    r = client.get("/reminders", headers=auth_header)
    assert r.status_code == 200
    reminders = r.get_json()
    followups = [x for x in reminders if "Autopay succeeded" in x["message"]]
    assert len(followups) == 2
    assert sorted([x["channel"] for x in followups]) == ["email", "whatsapp"]


def test_reminder_delivery_reliability_tracks_success_and_failure(
    client, auth_header, monkeypatch
):
    calls = []

    def fake_send(reminder):
        calls.append(reminder.channel)
        return reminder.channel == "user@example.com"

    monkeypatch.setattr("app.routes.reminders.send_reminder", fake_send)
    send_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()

    success = client.post(
        "/reminders",
        json={"message": "Pay rent", "send_at": send_at, "channel": "user@example.com"},
        headers=auth_header,
    )
    assert success.status_code == 201
    failure = client.post(
        "/reminders",
        json={"message": "Pay card", "send_at": send_at, "channel": "email"},
        headers=auth_header,
    )
    assert failure.status_code == 201

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == {"processed": 2, "delivered": 1, "failed": 1}
    assert sorted(calls) == ["email", "user@example.com"]

    r = client.get("/reminders", headers=auth_header)
    reminders = {item["message"]: item for item in r.get_json()}
    assert reminders["Pay rent"]["sent"] is True
    assert reminders["Pay rent"]["status"] == "DELIVERED"
    assert reminders["Pay rent"]["attempt_count"] == 1
    assert reminders["Pay rent"]["delivered_at"] is not None
    assert reminders["Pay card"]["sent"] is False
    assert reminders["Pay card"]["status"] == "FAILED"
    assert reminders["Pay card"]["failed_at"] is not None
    assert reminders["Pay card"]["last_error"] == "delivery adapter returned false"

    r = client.get("/reminders/reliability", headers=auth_header)
    assert r.status_code == 200
    metrics = r.get_json()
    assert metrics["totals"] == {
        "total": 2,
        "pending": 0,
        "delivered": 1,
        "failed": 1,
        "attempts": 2,
    }
    assert metrics["delivery_rate"] == 0.5
    assert metrics["by_channel"]["user@example.com"]["delivered"] == 1
    assert metrics["by_channel"]["email"]["failed"] == 1
