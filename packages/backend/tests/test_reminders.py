from datetime import date


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


def test_run_due_retry_logic(client, auth_header, mocker):
    from datetime import datetime, timedelta

    # Mock send_reminder to always return False
    mocker.patch("app.routes.reminders.send_reminder", return_value=False)

    # Create a reminder scheduled in the past
    payload = {
        "message": "Test retry logic",
        "send_at": (datetime.utcnow() - timedelta(minutes=10)).isoformat(),
        "channel": "email",
    }
    r = client.post("/reminders", json=payload, headers=auth_header)
    assert r.status_code == 201
    reminder_id = r.get_json()["id"]

    # First run (retry 1)
    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["processed"] >= 1

    r = client.get("/reminders", headers=auth_header)
    reminders = [x for x in r.get_json() if x["id"] == reminder_id]
    assert len(reminders) == 1
    assert reminders[0]["retry_count"] == 1
    assert reminders[0]["failed"] is False
    assert reminders[0]["sent"] is False

    # Second run (retry 2)
    client.post("/reminders/run", headers=auth_header)
    # Third run (retry 3) - should mark as failed
    client.post("/reminders/run", headers=auth_header)

    r = client.get("/reminders", headers=auth_header)
    reminders = [x for x in r.get_json() if x["id"] == reminder_id]
    assert reminders[0]["retry_count"] == 3
    assert reminders[0]["failed"] is True
    assert reminders[0]["sent"] is False

    # Fourth run - should NOT process the failed reminder
    r = client.post("/reminders/run", headers=auth_header)
    # the processed count for this specific one should be 0,
    # but other tests might have items.
    # We can check that retry_count is still 3
    r = client.get("/reminders", headers=auth_header)
    reminders = [x for x in r.get_json() if x["id"] == reminder_id]
    assert reminders[0]["retry_count"] == 3
