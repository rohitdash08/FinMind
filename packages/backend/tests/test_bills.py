from datetime import date


def test_bills_crud_and_mark_paid(client, auth_header):
    # Initially empty
    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create bill
    payload = {
        "name": "Internet",
        "amount": 49.99,
        "currency": "USD",
        "next_due_date": date.today().isoformat(),
        "cadence": "MONTHLY",
        "channel_email": True,
        "channel_whatsapp": False,
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 201
    bill_id = r.get_json()["id"]

    # List has 1
    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert any(b["id"] == bill_id for b in items)

    # Mark paid
    r = client.post(f"/bills/{bill_id}/pay", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "updated"


def test_bill_create_defaults_to_user_preferred_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "INR"}, headers=auth_header
    )
    assert r.status_code == 200

    payload = {
        "name": "Gas",
        "amount": 30.0,
        "next_due_date": date.today().isoformat(),
        "cadence": "MONTHLY",
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 201
    bill_id = r.get_json()["id"]

    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    created = next((item for item in r.get_json() if item["id"] == bill_id), None)
    assert created is not None
    assert created["currency"] == "INR"


def test_bill_create_rejects_invalid_input_with_400(client, auth_header):
    r = client.post(
        "/bills",
        json={"name": "", "amount": "oops", "next_due_date": "2026-02-31"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] in {
        "name required",
        "invalid amount",
        "invalid next_due_date",
    }


def test_bill_create_rejects_non_object_json_body(client, auth_header):
    r = client.post(
        "/bills",
        data='["bad"]',
        content_type="application/json",
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json() == {"error": "json body must be an object"}


def test_bill_create_normalizes_string_boolean_flags(client, auth_header):
    r = client.post(
        "/bills",
        json={
            "name": "Utilities",
            "amount": 22.0,
            "next_due_date": date.today().isoformat(),
            "cadence": "MONTHLY",
            "autopay_enabled": "false",
            "channel_email": "false",
            "channel_whatsapp": "true",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    bill_id = r.get_json()["id"]

    r = client.get("/bills", headers=auth_header)
    created = next(item for item in r.get_json() if item["id"] == bill_id)
    assert created["autopay_enabled"] is False
    assert created["channel_email"] is False
    assert created["channel_whatsapp"] is True
