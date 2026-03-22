from datetime import date, datetime, timedelta
from unittest.mock import patch


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


# --- Retry & Monitoring Tests ---


def _create_past_reminder(client, auth_header):
    """Create a reminder whose send_at is in the past (due now)."""
    r = client.post(
        "/reminders",
        json={
            "message": "Test reminder",
            "send_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "channel": "email",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()["id"]


def test_run_due_marks_sent_on_success(client, auth_header):
    rid = _create_past_reminder(client, auth_header)

    with patch("app.routes.reminders.send_reminder", return_value=True):
        r = client.post("/reminders/run", headers=auth_header)

    assert r.status_code == 200
    data = r.get_json()
    assert data["processed"] == 1
    assert data["succeeded"] == 1
    assert data["failed"] == 0

    # Verify reminder is now marked sent
    r = client.get("/reminders", headers=auth_header)
    reminder = next(x for x in r.get_json() if x["id"] == rid)
    assert reminder["sent"] is True
    assert reminder["retry_count"] == 0


def test_run_due_retries_on_failure_with_backoff(client, auth_header):
    rid = _create_past_reminder(client, auth_header)

    # First run: send fails -> should increment retry_count
    with patch("app.routes.reminders.send_reminder", return_value=False):
        r = client.post("/reminders/run", headers=auth_header)

    assert r.status_code == 200
    assert r.get_json()["failed"] == 1

    r = client.get("/reminders", headers=auth_header)
    reminder = next(x for x in r.get_json() if x["id"] == rid)
    assert reminder["sent"] is False
    assert reminder["retry_count"] == 1
    assert reminder["last_error"] == "send failed"

    # Second run immediately: should be skipped due to backoff (60s)
    with patch("app.routes.reminders.send_reminder", return_value=True) as mock_send:
        r = client.post("/reminders/run", headers=auth_header)
    assert r.get_json()["processed"] == 0  # skipped due to backoff

    # Manually adjust send_at to simulate backoff elapsed
    from app.extensions import db
    from app.models import Reminder

    with client.application.app_context():
        reminder_obj = db.session.get(Reminder, rid)
        reminder_obj.send_at = datetime.utcnow() - timedelta(minutes=10)
        db.session.commit()

    # Now retry should proceed
    with patch("app.routes.reminders.send_reminder", return_value=True):
        r = client.post("/reminders/run", headers=auth_header)
    assert r.get_json()["succeeded"] == 1


def test_run_due_exhausts_after_max_retries(client, auth_header):
    from app.models import MAX_RETRIES

    rid = _create_past_reminder(client, auth_header)

    # Run MAX_RETRIES times, all failing
    from app.extensions import db
    from app.models import Reminder

    for i in range(MAX_RETRIES):
        # Adjust send_at past backoff for each attempt
        with client.application.app_context():
            reminder_obj = db.session.get(Reminder, rid)
            reminder_obj.send_at = datetime.utcnow() - timedelta(hours=1)
            db.session.commit()

        with patch("app.routes.reminders.send_reminder", return_value=False):
            client.post("/reminders/run", headers=auth_header)

    r = client.get("/reminders", headers=auth_header)
    reminder = next(x for x in r.get_json() if x["id"] == rid)
    assert reminder["sent"] is False
    assert reminder["retry_count"] == MAX_RETRIES
    assert reminder["exhausted"] is True


def test_run_due_handles_exception_in_send(client, auth_header):
    rid = _create_past_reminder(client, auth_header)

    with patch(
        "app.routes.reminders.send_reminder", side_effect=RuntimeError("SMTP down")
    ):
        r = client.post("/reminders/run", headers=auth_header)

    assert r.status_code == 200
    assert r.get_json()["failed"] == 1

    r = client.get("/reminders", headers=auth_header)
    reminder = next(x for x in r.get_json() if x["id"] == rid)
    assert reminder["retry_count"] == 1
    assert reminder["last_error"] == "SMTP down"


def test_reminder_stats_endpoint(client, auth_header):
    # Create a due reminder and send it successfully
    _create_past_reminder(client, auth_header)
    with patch("app.routes.reminders.send_reminder", return_value=True):
        client.post("/reminders/run", headers=auth_header)

    # Create a second reminder that hasn't been processed yet
    _create_past_reminder(client, auth_header)

    # Fetch stats
    r = client.get("/reminders/stats", headers=auth_header)
    assert r.status_code == 200
    stats = r.get_json()
    assert stats["total"] == 2
    assert stats["sent"] == 1
    assert stats["pending"] == 1
    assert stats["exhausted"] == 0
    assert stats["retrying"] == 0
    assert stats["max_retries"] == 3
    assert "email" in stats["channels"]


def test_manual_retry_resets_exhausted_reminder(client, auth_header):
    from app.models import MAX_RETRIES

    rid = _create_past_reminder(client, auth_header)

    from app.extensions import db
    from app.models import Reminder

    # Exhaust retries
    for i in range(MAX_RETRIES):
        with client.application.app_context():
            reminder_obj = db.session.get(Reminder, rid)
            reminder_obj.send_at = datetime.utcnow() - timedelta(hours=1)
            db.session.commit()
        with patch("app.routes.reminders.send_reminder", return_value=False):
            client.post("/reminders/run", headers=auth_header)

    # Verify exhausted
    r = client.get("/reminders", headers=auth_header)
    assert next(x for x in r.get_json() if x["id"] == rid)["exhausted"] is True

    # Manual retry
    r = client.post(f"/reminders/{rid}/retry", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["retry_count"] == 0

    # Now it should be pending again
    r = client.get("/reminders/stats", headers=auth_header)
    assert r.get_json()["pending"] == 1
    assert r.get_json()["exhausted"] == 0
