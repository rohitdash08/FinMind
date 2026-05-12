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


def test_run_due_retries_failed_delivery_and_exposes_job_status(
    client, auth_header, monkeypatch
):
    from app.services import reminder_jobs

    bill_id = _create_bill(client, auth_header, due_date="2026-03-20")
    r = client.post(
        f"/reminders/bills/{bill_id}/autopay-result",
        json={"status": "FAILED"},
        headers=auth_header,
    )
    assert r.status_code == 200

    def process_with_failure(reminders, *, now):
        return reminder_jobs.process_due_reminders(
            reminders, now=now, sender=lambda reminder: False
        )

    monkeypatch.setattr(
        "app.routes.reminders.process_due_reminders", process_with_failure
    )

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["processed"] == 2
    assert r.get_json()["retry_scheduled"] == 2
    assert r.get_json()["sent"] == 0

    r = client.get("/reminders/jobs", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["retrying"] == 2
    assert r.get_json()["failed"] == 0

    r = client.get("/reminders", headers=auth_header)
    reminders = r.get_json()
    assert all(item["retry_count"] == 1 for item in reminders)
    assert all(item["next_retry_at"] for item in reminders)
    assert all(item["sent"] is False for item in reminders)


def test_retry_failed_reminder_resets_failure_state(client, auth_header, monkeypatch):
    from app.services import reminder_jobs

    bill_id = _create_bill(client, auth_header, due_date="2026-03-20")
    r = client.post(
        f"/reminders/bills/{bill_id}/autopay-result",
        json={"status": "FAILED"},
        headers=auth_header,
    )
    assert r.status_code == 200

    def always_fail(reminder):
        reminder.max_retries = 1
        return False

    def process_with_failure(reminders, *, now):
        return reminder_jobs.process_due_reminders(
            reminders, now=now, sender=always_fail
        )

    monkeypatch.setattr(
        "app.routes.reminders.process_due_reminders", process_with_failure
    )

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["failed"] == 2

    reminder_id = client.get("/reminders", headers=auth_header).get_json()[0]["id"]
    r = client.post(f"/reminders/{reminder_id}/retry", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == {"id": reminder_id, "retry_scheduled": True}

    reminder = [
        item
        for item in client.get("/reminders", headers=auth_header).get_json()
        if item["id"] == reminder_id
    ][0]
    assert reminder["failed"] is False
    assert reminder["retry_count"] == 0
    assert reminder["last_error"] is None
    assert reminder["next_retry_at"] is not None
