from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import Reminder


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


def test_due_reminder_retries_then_dead_letters_failed_delivery(
    client, auth_header, monkeypatch, app_fixture
):
    monkeypatch.setattr("app.services.reminders.send_email", lambda *args: False)

    r = client.post(
        "/reminders",
        json={
            "message": "Retry me",
            "send_at": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            "channel": "email",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    reminder_id = r.get_json()["id"]

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["retrying"] == 1

    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.sent is False
        assert reminder.failed is False
        assert reminder.retry_count == 1
        assert reminder.next_retry_at is not None
        reminder.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["retrying"] == 1

    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        reminder.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["failed"] == 1

    r = client.get("/reminders/jobs/status", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["failed"] == 1

    r = client.get("/reminders/jobs/failed", headers=auth_header)
    assert r.status_code == 200
    failed_jobs = r.get_json()
    assert failed_jobs[0]["id"] == reminder_id
    assert failed_jobs[0]["retry_count"] == 3

    r = client.post(f"/reminders/jobs/{reminder_id}/retry", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["failed"] is False

    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.retry_count == 0
        assert reminder.failed is False
        assert reminder.last_error is None


def test_due_reminder_marks_successful_delivery_sent(client, auth_header, monkeypatch):
    monkeypatch.setattr("app.services.reminders.send_email", lambda *args: True)

    r = client.post(
        "/reminders",
        json={
            "message": "Send me",
            "send_at": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            "channel": "email",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["sent"] == 1

    r = client.get("/reminders", headers=auth_header)
    assert r.status_code == 200
    reminder = r.get_json()[0]
    assert reminder["sent"] is True
    assert reminder["sent_at"] is not None
    assert reminder["retry_count"] == 0
