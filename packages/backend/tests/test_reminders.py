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


def _create_reminder(client, auth_header, *, send_at=None, channel="email"):
    payload = {
        "message": "Pay card",
        "send_at": (send_at or datetime.utcnow() - timedelta(minutes=5)).isoformat(),
        "channel": channel,
    }
    r = client.post("/reminders", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def _login(client, email: str):
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


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


def test_run_due_retries_failed_reminders_without_marking_sent(
    app_fixture, client, auth_header, monkeypatch
):
    reminder_id = _create_reminder(client, auth_header)
    monkeypatch.setattr("app.services.reminder_jobs.send_reminder", lambda _r: False)

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == {"processed": 1, "sent": 0, "retrying": 1, "failed": 0}

    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.sent is False
        assert reminder.job_status == "RETRYING"
        assert reminder.retry_count == 1
        assert reminder.next_retry_at is not None
        assert reminder.last_error == "send_reminder returned false"

    stats = client.get("/reminders/jobs/stats", headers=auth_header).get_json()
    assert stats["retrying"] == 1
    assert stats["due_now"] == 0
    assert stats["next_retry_at"] is not None

    jobs = client.get("/reminders/jobs?status=RETRYING", headers=auth_header).get_json()
    assert [job["id"] for job in jobs] == [reminder_id]


def test_retry_backoff_waits_until_next_retry_window(
    app_fixture, client, auth_header, monkeypatch
):
    reminder_id = _create_reminder(client, auth_header)
    monkeypatch.setattr("app.services.reminder_jobs.send_reminder", lambda _r: False)

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["retrying"] == 1

    monkeypatch.setattr("app.services.reminder_jobs.send_reminder", lambda _r: True)
    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["processed"] == 0

    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        reminder.next_retry_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["sent"] == 1

    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.sent is True
        assert reminder.job_status == "SENT"
        assert reminder.sent_at is not None
        assert reminder.next_retry_at is None
        assert reminder.last_error is None


def test_max_attempts_failure_can_be_manually_retried(
    app_fixture, client, auth_header, monkeypatch
):
    reminder_id = _create_reminder(client, auth_header)
    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        reminder.max_attempts = 1
        db.session.commit()
    monkeypatch.setattr(
        "app.services.reminder_jobs.send_reminder",
        lambda _r: (_ for _ in ()).throw(RuntimeError("provider down")),
    )

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == {"processed": 1, "sent": 0, "retrying": 0, "failed": 1}

    with app_fixture.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.job_status == "FAILED"
        assert reminder.failed_at is not None
        assert reminder.last_error == "provider down"

    failed = client.get("/reminders/jobs?status=FAILED", headers=auth_header)
    assert failed.status_code == 200
    assert failed.get_json()[0]["id"] == reminder_id

    r = client.post(f"/reminders/{reminder_id}/retry", headers=auth_header)
    assert r.status_code == 200
    retry_payload = r.get_json()
    assert retry_payload["job_status"] == "PENDING"
    assert retry_payload["retry_count"] == 0
    assert retry_payload["last_error"] is None

    monkeypatch.setattr("app.services.reminder_jobs.send_reminder", lambda _r: True)
    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["sent"] == 1


def test_reminder_job_monitoring_is_user_scoped(client, auth_header):
    first_id = _create_reminder(client, auth_header)
    other_header = _login(client, "other@example.com")
    other_id = _create_reminder(client, other_header)

    first_jobs = client.get("/reminders/jobs", headers=auth_header)
    assert first_jobs.status_code == 200
    assert [job["id"] for job in first_jobs.get_json()] == [first_id]

    other_jobs = client.get("/reminders/jobs", headers=other_header)
    assert other_jobs.status_code == 200
    assert [job["id"] for job in other_jobs.get_json()] == [other_id]

    r = client.post(f"/reminders/{other_id}/retry", headers=auth_header)
    assert r.status_code == 404
