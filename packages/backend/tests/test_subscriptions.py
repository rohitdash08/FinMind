from datetime import date, timedelta


def _create_expense(client, auth_header, amount, notes, days_ago):
    spent_at = (date.today() - timedelta(days=days_ago)).isoformat()
    r = client.post(
        "/expenses",
        json={"amount": amount, "description": notes, "date": spent_at},
        headers=auth_header,
    )
    return r.get_json()


def test_detect_subscriptions(client, auth_header):
    _create_expense(client, auth_header, 9.99, "Netflix", 30)
    _create_expense(client, auth_header, 9.99, "Netflix", 60)
    _create_expense(client, auth_header, 9.99, "Netflix", 90)

    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["count"] >= 1
    names = [s["name"] for s in data["detected"]]
    assert "Netflix" in names


def test_list_detected(client, auth_header):
    _create_expense(client, auth_header, 5.99, "Spotify", 30)
    _create_expense(client, auth_header, 5.99, "Spotify", 60)
    client.post("/subscriptions/detect", headers=auth_header)

    r = client.get("/subscriptions/detected", headers=auth_header)
    assert r.status_code == 200


def test_confirm_subscription(client, auth_header):
    _create_expense(client, auth_header, 5.99, "Dropbox", 30)
    _create_expense(client, auth_header, 5.99, "Dropbox", 60)
    r = client.post("/subscriptions/detect", headers=auth_header)
    subs = r.get_json()["detected"]
    if subs:
        sub_id = subs[0]["id"]
        r = client.post(f"/subscriptions/detected/{sub_id}/confirm", headers=auth_header)
        assert r.status_code == 200


def test_price_history(client, auth_header):
    _create_expense(client, auth_header, 14.99, "Adobe", 30)
    _create_expense(client, auth_header, 14.99, "Adobe", 60)
    r = client.post("/subscriptions/detect", headers=auth_header)
    subs = r.get_json()["detected"]
    if subs:
        sub_id = subs[0]["id"]
        r = client.get(f"/subscriptions/detected/{sub_id}/price-history", headers=auth_header)
        assert r.status_code == 200


def test_price_increases(client, auth_header):
    r = client.get("/subscriptions/price-increases", headers=auth_header)
    assert r.status_code == 200
