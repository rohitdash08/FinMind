from datetime import date


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


def test_detect_cost_increase(client, auth_header):
    """A merchant whose latest charge is higher should be flagged."""
    _create_expense(client, auth_header, "Spotify", 9.99, date(2025, 1, 15))
    _create_expense(client, auth_header, "Spotify", 10.99, date(2025, 2, 15))

    r = client.get("/cost-increases", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 1
    assert data[0]["merchant"] == "Spotify"
    assert data[0]["previous_amount"] == 9.99
    assert data[0]["current_amount"] == 10.99
    assert data[0]["increase"] == 1.0
    assert data[0]["increase_pct"] > 0


def test_no_increase_when_price_drops(client, auth_header):
    """A price decrease should not be flagged."""
    _create_expense(client, auth_header, "Hulu", 14.99, date(2025, 1, 1))
    _create_expense(client, auth_header, "Hulu", 12.99, date(2025, 2, 1))

    r = client.get("/cost-increases", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    merchants = [d["merchant"] for d in data]
    assert "Hulu" not in merchants


def test_no_increase_when_same_price(client, auth_header):
    """Same price should not be flagged."""
    _create_expense(client, auth_header, "Netflix", 15.99, date(2025, 1, 1))
    _create_expense(client, auth_header, "Netflix", 15.99, date(2025, 2, 1))

    r = client.get("/cost-increases", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    merchants = [d["merchant"] for d in data]
    assert "Netflix" not in merchants


def test_cost_increase_empty(client, auth_header):
    """No expenses should return empty list."""
    r = client.get("/cost-increases", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_cost_increase_min_history(client, auth_header):
    """Single charge should not be enough to detect increase."""
    _create_expense(client, auth_header, "Disney+", 7.99, date(2025, 3, 1))

    r = client.get("/cost-increases", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []
