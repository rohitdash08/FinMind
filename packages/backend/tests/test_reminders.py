from datetime import date, datetime
from app.models import Expense
from app.extensions import db


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


def test_smart_reminder_timing_based_on_user_behavior(client, auth_header, app_fixture):
    # Create some expenses at a specific hour, e.g., 14:00
    with app_fixture.app_context():
        # Get user id 1
        for _ in range(5):
            e = Expense(
                user_id=1,
                amount=10.0,
                created_at=datetime.utcnow().replace(hour=14, minute=30, second=0),
            )
            db.session.add(e)
        db.session.commit()

    bill_id = _create_bill(client, auth_header, due_date="2026-04-10")

    r = client.post(f"/reminders/bills/{bill_id}/schedule", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/reminders", headers=auth_header)
    assert r.status_code == 200
    reminders = r.get_json()

    # Filter for the newly scheduled bill reminders
    # (we might have old ones from previous tests)
    bill_reminders = [
        x
        for x in reminders
        if "Upcoming bill reminder" in x["message"]
        and "2026-04-10" in x["message"]
    ]
    assert len(bill_reminders) > 0

    for rem in bill_reminders:
        dt = datetime.fromisoformat(rem["send_at"])
        assert dt.hour == 14
