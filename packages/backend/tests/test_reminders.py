from datetime import date, datetime, timedelta

import app.routes.reminders as reminder_routes


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


def test_due_reminders_retry_failures_without_blocking_successes(
    client, auth_header, monkeypatch
):
    due = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    for message in ("send ok", "fail once"):
        r = client.post(
            "/reminders",
            json={"message": message, "send_at": due, "channel": "email"},
            headers=auth_header,
        )
        assert r.status_code == 201

    def fake_send(reminder):
        if reminder.message == "fail once":
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(reminder_routes, "send_reminder", fake_send)

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == {"processed": 2, "sent": 1, "retrying": 1, "failed": 0}

    r = client.get("/reminders", headers=auth_header)
    reminders = {item["message"]: item for item in r.get_json()}
    assert reminders["send ok"]["sent"] is True
    assert reminders["fail once"]["sent"] is False
    assert reminders["fail once"]["failed"] is False
    assert reminders["fail once"]["retry_count"] == 1
    assert reminders["fail once"]["next_retry_at"] is not None
    assert reminders["fail once"]["last_error"] == "provider unavailable"


def test_due_reminders_move_to_dead_letter_and_can_be_retried(
    client, auth_header, monkeypatch
):
    due = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    r = client.post(
        "/reminders",
        json={"message": "always fail", "send_at": due, "channel": "email"},
        headers=auth_header,
    )
    assert r.status_code == 201
    reminder_id = r.get_json()["id"]

    def fake_send(_reminder):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(reminder_routes, "send_reminder", fake_send)

    for _ in range(3):
        r = client.post("/reminders/run", headers=auth_header)
        assert r.status_code == 200
        with client.application.app_context():
            from app.extensions import db
            from app.models import Reminder

            reminder = db.session.get(Reminder, reminder_id)
            reminder.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
            db.session.commit()

    r = client.get("/reminders/jobs", headers=auth_header)
    assert r.status_code == 200
    jobs = r.get_json()
    assert jobs["summary"]["failed"] == 1
    assert jobs["summary"]["retrying"] == 0
    assert jobs["dead_letter"][0]["id"] == reminder_id
    assert jobs["dead_letter"][0]["last_error"] == "smtp down"

    r = client.post(f"/reminders/{reminder_id}/retry", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["failed"] is False
    assert payload["retry_count"] == 0
    assert payload["last_error"] is None
