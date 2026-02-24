from datetime import date, timedelta


def _create_expense(client, auth_header, description, amount, spent_at):
    return client.post(
        "/expenses",
        json={
            "description": description,
            "amount": amount,
            "date": spent_at.isoformat(),
        },
        headers=auth_header,
    )


def test_detect_subscriptions_finds_monthly_pattern(client, auth_header):
    """Three identical charges ~30 days apart should be detected."""
    base = date(2025, 1, 15)
    for i in range(3):
        r = _create_expense(
            client, auth_header, "Netflix", 15.99, base + timedelta(days=30 * i)
        )
        assert r.status_code == 201

    r = client.get("/subscriptions/detect", headers=auth_header)
    assert r.status_code == 200
    subs = r.get_json()
    assert len(subs) == 1
    assert subs[0]["merchant"] == "Netflix"
    assert subs[0]["amount"] == 15.99
    assert subs[0]["cadence"] == "MONTHLY"
    assert subs[0]["occurrences"] == 3


def test_detect_subscriptions_ignores_irregular(client, auth_header):
    """Charges with irregular gaps should not be detected."""
    dates = [date(2025, 1, 1), date(2025, 2, 1), date(2025, 5, 20)]
    for d in dates:
        r = _create_expense(client, auth_header, "RandomShop", 25.00, d)
        assert r.status_code == 201

    r = client.get("/subscriptions/detect", headers=auth_header)
    assert r.status_code == 200
    subs = r.get_json()
    merchants = [s["merchant"] for s in subs]
    assert "RandomShop" not in merchants


def test_detect_subscriptions_empty(client, auth_header):
    """No expenses should return empty list."""
    r = client.get("/subscriptions/detect", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_detect_subscriptions_weekly(client, auth_header):
    """Weekly recurring charges should be detected."""
    base = date(2025, 3, 1)
    for i in range(4):
        r = _create_expense(
            client, auth_header, "Gym", 10.00, base + timedelta(weeks=i)
        )
        assert r.status_code == 201

    r = client.get(
        "/subscriptions/detect?min_occurrences=3&tolerance_days=2",
        headers=auth_header,
    )
    assert r.status_code == 200
    subs = r.get_json()
    gym = [s for s in subs if s["merchant"] == "Gym"]
    assert len(gym) == 1
    assert gym[0]["cadence"] == "WEEKLY"
