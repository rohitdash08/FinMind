from datetime import date, datetime, timedelta

from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import User


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


def _auth_header_without_redis(app_fixture):
    with app_fixture.app_context():
        user = User(email="retry@example.com", password_hash="unused")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def test_run_due_retries_transient_delivery_failures(client, app_fixture, monkeypatch):
    attempts = {"count": 0}

    def flaky_send(_reminder):
        attempts["count"] += 1
        return attempts["count"] >= 3

    monkeypatch.setattr("app.routes.reminders.send_reminder", flaky_send)
    auth_header = _auth_header_without_redis(app_fixture)
    send_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    r = client.post(
        "/reminders",
        json={"message": "Retry me", "send_at": send_at, "channel": "email"},
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload == {"processed": 1, "sent": 1, "failed": 0, "retries": 2}
    assert attempts["count"] == 3

    r = client.get("/reminders", headers=auth_header)
    reminder = r.get_json()[0]
    assert reminder["sent"] is True
    assert reminder["delivery_attempts"] == 3
    assert reminder["last_error"] is None


def test_run_due_keeps_failed_reminders_unsent(client, app_fixture, monkeypatch):
    def failed_send(_reminder):
        raise RuntimeError("smtp timeout")

    monkeypatch.setattr("app.routes.reminders.send_reminder", failed_send)
    auth_header = _auth_header_without_redis(app_fixture)
    send_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    r = client.post(
        "/reminders",
        json={"message": "Do not mark sent", "send_at": send_at, "channel": "email"},
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload == {"processed": 1, "sent": 0, "failed": 1, "retries": 2}

    r = client.get("/reminders", headers=auth_header)
    reminder = r.get_json()[0]
    assert reminder["sent"] is False
    assert reminder["delivery_attempts"] == 3
    assert reminder["last_error"] == "smtp timeout"
