from datetime import date
from datetime import datetime, timedelta


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


def test_due_reminders_retry_failed_send_and_expose_health(
    client, auth_header, monkeypatch
):
    attempts = {"count": 0}

    def fake_send(_reminder):
        attempts["count"] += 1
        return False

    monkeypatch.setattr("app.routes.reminders.send_reminder", fake_send)
    send_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    created = client.post(
        "/reminders",
        json={
            "message": "Retry me",
            "send_at": send_at,
            "channel": "email",
            "max_attempts": 2,
        },
        headers=auth_header,
    )
    assert created.status_code == 201

    run = client.post("/reminders/run", headers=auth_header)
    assert run.status_code == 200
    assert run.get_json() == {"processed": 1, "sent": 0, "failed": 1, "retried": 1}
    assert attempts["count"] == 1

    listed = client.get("/reminders", headers=auth_header)
    reminder = listed.get_json()[0]
    assert reminder["sent"] is False
    assert reminder["retry_count"] == 1
    assert reminder["max_attempts"] == 2
    assert reminder["last_error"] == "provider returned false"
    assert datetime.fromisoformat(reminder["send_at"]) > datetime.utcnow()

    health = client.get("/reminders/jobs/health", headers=auth_header)
    assert health.status_code == 200
    assert health.get_json() == {"due": 0, "exhausted": 0}


def test_due_reminders_mark_exhausted_after_max_attempts(
    client, auth_header, monkeypatch
):
    monkeypatch.setattr("app.routes.reminders.send_reminder", lambda _reminder: False)
    send_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    created = client.post(
        "/reminders",
        json={
            "message": "Do not retry",
            "send_at": send_at,
            "channel": "email",
            "max_attempts": 1,
        },
        headers=auth_header,
    )
    assert created.status_code == 201

    run = client.post("/reminders/run", headers=auth_header)
    assert run.status_code == 200
    assert run.get_json() == {"processed": 1, "sent": 0, "failed": 1, "retried": 0}

    health = client.get("/reminders/jobs/health", headers=auth_header)
    assert health.status_code == 200
    assert health.get_json() == {"due": 0, "exhausted": 1}


def test_due_reminders_clear_retry_state_on_success(client, auth_header, monkeypatch):
    monkeypatch.setattr("app.routes.reminders.send_reminder", lambda _reminder: True)
    send_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    created = client.post(
        "/reminders",
        json={"message": "Send me", "send_at": send_at, "channel": "email"},
        headers=auth_header,
    )
    assert created.status_code == 201

    run = client.post("/reminders/run", headers=auth_header)
    assert run.status_code == 200
    assert run.get_json() == {"processed": 1, "sent": 1, "failed": 0, "retried": 0}

    listed = client.get("/reminders", headers=auth_header)
    reminder = listed.get_json()[0]
    assert reminder["sent"] is True
    assert reminder["retry_count"] == 0
    assert reminder["last_error"] is None
