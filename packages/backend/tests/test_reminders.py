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


def test_due_reminders_retry_when_sender_fails(client, auth_header, monkeypatch):
    monkeypatch.setattr(
        "app.routes.reminders.send_reminder",
        lambda _reminder: False,
    )
    r = _create_due_reminder(client, auth_header)
    reminder_id = r["id"]

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == {"processed": 1, "sent": 0, "retrying": 1, "failed": 0}

    r = client.get("/reminders", headers=auth_header)
    reminder = next(x for x in r.get_json() if x["id"] == reminder_id)
    assert reminder["sent"] is False
    assert reminder["retry_status"] == "RETRYING"
    assert reminder["retry_count"] == 1
    assert reminder["next_retry_at"] is not None
    assert reminder["last_error"] == "sender returned false"


def test_retrying_reminder_sends_after_backoff(
    client, auth_header, app_fixture, monkeypatch
):
    outcomes = iter([False, True])
    monkeypatch.setattr(
        "app.routes.reminders.send_reminder",
        lambda _reminder: next(outcomes),
    )
    reminder_id = _create_due_reminder(client, auth_header)["id"]

    first = client.post("/reminders/run", headers=auth_header)
    assert first.get_json()["retrying"] == 1

    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        reminder.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

    second = client.post("/reminders/run", headers=auth_header)
    assert second.status_code == 200
    assert second.get_json() == {"processed": 1, "sent": 1, "retrying": 0, "failed": 0}

    r = client.get("/reminders", headers=auth_header)
    reminder = next(x for x in r.get_json() if x["id"] == reminder_id)
    assert reminder["sent"] is True
    assert reminder["retry_status"] == "SENT"
    assert reminder["last_error"] is None


def test_failed_jobs_endpoint_and_manual_retry(client, auth_header, app_fixture):
    reminder_id = _create_due_reminder(client, auth_header)["id"]
    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        reminder.retry_status = "FAILED"
        reminder.retry_count = 3
        reminder.max_retries = 3
        reminder.last_error = "smtp timeout"
        reminder.failed_at = datetime.utcnow()
        db.session.commit()

    r = client.get("/reminders/jobs/status", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["failed"] == 1
    assert r.get_json()["healthy"] is False

    r = client.get("/reminders/jobs/failed", headers=auth_header)
    assert r.status_code == 200
    failed = r.get_json()
    assert len(failed) == 1
    assert failed[0]["id"] == reminder_id
    assert failed[0]["last_error"] == "smtp timeout"

    r = client.post(f"/reminders/jobs/{reminder_id}/retry", headers=auth_header)
    assert r.status_code == 200
    retried = r.get_json()
    assert retried["retry_status"] == "PENDING"
    assert retried["retry_count"] == 0
    assert retried["last_error"] is None


def test_failed_jobs_are_user_scoped(client, auth_header, app_fixture):
    first_id = _create_due_reminder(client, auth_header, message="First")["id"]
    second_header = _register_and_login(client, "other@example.com")
    second_id = _create_due_reminder(client, second_header, message="Second")["id"]
    with app_fixture.app_context():
        for reminder_id in (first_id, second_id):
            reminder = db.session.get(Reminder, reminder_id)
            reminder.retry_status = "FAILED"
            reminder.retry_count = 3
            reminder.failed_at = datetime.utcnow()
        db.session.commit()

    r = client.get("/reminders/jobs/failed", headers=auth_header)
    assert [item["id"] for item in r.get_json()] == [first_id]

    r = client.post(f"/reminders/jobs/{second_id}/retry", headers=auth_header)
    assert r.status_code == 404


def _create_due_reminder(client, auth_header, *, message: str = "Pay rent"):
    r = client.post(
        "/reminders",
        json={
            "message": message,
            "send_at": (datetime.utcnow() - timedelta(minutes=2)).isoformat(),
            "channel": "email",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()


def _register_and_login(client, email: str):
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}
