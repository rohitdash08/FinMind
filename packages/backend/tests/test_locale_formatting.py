def test_expense_response_includes_locale_aware_formatting(client, auth_header):
    r = client.post(
        "/expenses?locale=de-DE",
        json={
            "amount": 1234.5,
            "currency": "EUR",
            "description": "Bahncard",
            "date": "2026-04-24",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    created = r.get_json()
    assert created["formatted"]["locale"] == "de-DE"
    assert created["formatted"]["amount_formatted"] == "1.234,50 €"
    assert created["formatted"]["date"] == "24.04.2026"

    r = client.get("/expenses", headers={**auth_header, "Accept-Language": "en-US"})
    assert r.status_code == 200
    item = r.get_json()[0]
    assert item["formatted"]["locale"] == "en-US"
    assert item["formatted"]["amount_formatted"] == "€1,234.50"
    assert item["formatted"]["date"] == "04/24/2026"


def test_dashboard_summary_includes_locale_metadata(client, auth_header):
    client.post(
        "/expenses",
        json={
            "amount": 1234567.89,
            "currency": "INR",
            "description": "Salary",
            "expense_type": "INCOME",
            "date": "2026-04-10",
        },
        headers=auth_header,
    )

    r = client.get("/dashboard/summary?month=2026-04&locale=en-IN", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["locale"] == "en-IN"
    assert payload["period"]["month_formatted"] == "01/04/2026"
    assert (
        payload["summary_formatted"]["monthly_income"]["amount_formatted"]
        == "₹12,34,567.89"
    )
    assert (
        payload["recent_transactions"][0]["formatted"]["amount_formatted"]
        == "₹12,34,567.89"
    )
