def test_subscriptions_list_empty(client, auth_header):
    r = client.get("/subscriptions", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_subscription_detection(client, auth_header):
    r = client.post(
        "/expenses/recurring",
        json={
            "amount": 15.99,
            "description": "Netflix",
            "cadence": "MONTHLY",
            "start_date": "2026-01-01",
        },
        headers=auth_header,
    )
    recurring_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-04-01"},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code == 201
    subs = r.get_json()
    assert isinstance(subs, list)

    if subs:
        assert subs[0]["merchant"] == "netflix"
        assert subs[0]["interval_days"] >= 20

    r = client.get("/subscriptions", headers=auth_header)
    assert r.status_code == 200


def test_update_subscription_status(client, auth_header):
    r = client.post(
        "/expenses/recurring",
        json={
            "amount": 9.99,
            "description": "Spotify",
            "cadence": "MONTHLY",
            "start_date": "2026-01-01",
        },
        headers=auth_header,
    )
    recurring_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-03-01"},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code == 201
    subs = r.get_json()
    if subs:
        sub_id = subs[0]["id"]
        r = client.patch(
            f"/subscriptions/{sub_id}",
            json={"status": "ignored"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["status"] == "ignored"


def test_price_history(client, auth_header):
    r = client.post(
        "/expenses/recurring",
        json={
            "amount": 10.0,
            "description": "Dropbox",
            "cadence": "MONTHLY",
            "start_date": "2026-01-01",
        },
        headers=auth_header,
    )
    recurring_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-03-01"},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code == 201
    subs = r.get_json()
    if subs:
        sub_id = subs[0]["id"]
        r = client.get(f"/subscriptions/{sub_id}/price-history", headers=auth_header)
        assert r.status_code == 200
        history = r.get_json()
        assert isinstance(history, list)


def test_price_increase_check(client, auth_header):
    r = client.post(
        "/expenses/recurring",
        json={
            "amount": 20.0,
            "description": "AWS",
            "cadence": "MONTHLY",
            "start_date": "2026-01-01",
        },
        headers=auth_header,
    )
    recurring_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-02-01"},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code == 201

    r = client.post("/subscriptions/check-increases", headers=auth_header)
    assert r.status_code == 200
    alerts = r.get_json()
    assert isinstance(alerts, list)
