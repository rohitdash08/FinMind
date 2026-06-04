def test_bank_connector_registry_lists_mock_connector(client, auth_header):
    r = client.get("/expenses/bank-connectors", headers=auth_header)
    assert r.status_code == 200
    connectors = r.get_json()
    by_key = {connector["key"]: connector for connector in connectors}
    assert by_key["mock"]["supports_refresh"] is True
    assert by_key["account_aggregator"]["supports_refresh"] is True


def test_account_aggregator_connector_imports_normalized_provider_payload(
    client, auth_header
):
    payload = {
        "connector_key": "account_aggregator",
        "config": {
            "provider_name": "Setu AA",
            "account_ref": "masked:XXXX1234",
            "display_name": "HDFC Savings",
            "currency": "INR",
            "consent_handle": "consent-123",
            "transactions": [
                {
                    "external_id": "aa-1",
                    "posted_at": "2026-04-01",
                    "amount": "-299.00",
                    "description": "UPI Grocery Store",
                    "currency": "INR",
                }
            ],
        },
    }

    r = client.post("/expenses/bank-connections", json=payload, headers=auth_header)
    assert r.status_code == 201
    connection = r.get_json()
    assert connection["connector_key"] == "account_aggregator"
    assert connection["display_name"] == "HDFC Savings"

    r = client.post(
        f"/expenses/bank-connections/{connection['id']}/import",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["inserted"] == 1

    r = client.get("/expenses?search=UPI%20Grocery", headers=auth_header)
    assert r.status_code == 200
    expenses = r.get_json()
    assert expenses[0]["currency"] == "INR"
    assert expenses[0]["description"] == "UPI Grocery Store"


def test_account_aggregator_requires_provider_identity(client, auth_header):
    r = client.post(
        "/expenses/bank-connections",
        json={
            "connector_key": "account_aggregator",
            "config": {"account_ref": "masked:XXXX1234"},
        },
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "provider_name required"


def test_mock_bank_connection_import_and_refresh_prevent_duplicates(
    client, auth_header
):
    payload = {
        "connector_key": "mock",
        "config": {
            "account_name": "Test Checking",
            "currency": "USD",
            "transactions": [
                {
                    "external_id": "tx-1",
                    "date": "2026-03-01",
                    "amount": "-11.25",
                    "description": "Card Coffee",
                },
                {
                    "external_id": "tx-2",
                    "date": "2026-03-02",
                    "amount": "1500.00",
                    "description": "Payroll",
                    "expense_type": "INCOME",
                },
            ],
        },
    }
    r = client.post("/expenses/bank-connections", json=payload, headers=auth_header)
    assert r.status_code == 201
    connection = r.get_json()
    assert connection["connector_key"] == "mock"
    assert connection["display_name"] == "Test Checking"
    connection_id = connection["id"]

    r = client.get("/expenses/bank-connections", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()[0]["id"] == connection_id

    r = client.post(
        f"/expenses/bank-connections/{connection_id}/import",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 201
    imported = r.get_json()
    assert imported["inserted"] == 2
    assert imported["duplicates"] == 0
    assert imported["status"] == "completed"

    r = client.post(
        f"/expenses/bank-connections/{connection_id}/import",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 201
    second_import = r.get_json()
    assert second_import["inserted"] == 0
    assert second_import["duplicates"] == 2

    r = client.post(
        f"/expenses/bank-connections/{connection_id}/refresh",
        headers=auth_header,
    )
    assert r.status_code == 200
    refreshed = r.get_json()
    assert refreshed["inserted"] == 0
    assert refreshed["duplicates"] == 0

    r = client.get("/expenses?search=Card%20Coffee", headers=auth_header)
    assert r.status_code == 200
    expenses = r.get_json()
    assert len(expenses) == 1
    assert expenses[0]["description"] == "Card Coffee"
    assert expenses[0]["amount"] == 11.25


def test_bank_connection_rejects_unknown_connector(client, auth_header):
    r = client.post(
        "/expenses/bank-connections",
        json={"connector_key": "plaid", "config": {}},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "unsupported connector"


def test_bank_connection_import_since_filter_and_invalid_since(client, auth_header):
    r = client.post(
        "/expenses/bank-connections",
        json={
            "connector_key": "mock",
            "config": {
                "transactions": [
                    {
                        "external_id": "old",
                        "date": "2026-01-01",
                        "amount": "-10.00",
                        "description": "Old card charge",
                    },
                    {
                        "external_id": "new",
                        "date": "2026-02-01",
                        "amount": "-20.00",
                        "description": "New card charge",
                    },
                ]
            },
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    connection_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/bank-connections/{connection_id}/import",
        json={"since": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid since"

    r = client.post(
        f"/expenses/bank-connections/{connection_id}/import",
        json={"since": "2026-02-01"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["inserted"] == 1

    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    descriptions = [item["description"] for item in r.get_json()]
    assert descriptions == ["New card charge"]


def test_bank_connection_cannot_import_another_users_connection(client, auth_header):
    r = client.post(
        "/expenses/bank-connections",
        json={"connector_key": "mock", "config": {"account_name": "Private Bank"}},
        headers=auth_header,
    )
    assert r.status_code == 201
    connection_id = r.get_json()["id"]

    client.post(
        "/auth/register",
        json={"email": "other@example.com", "password": "password123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": "other@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    other_auth = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = client.post(
        f"/expenses/bank-connections/{connection_id}/import",
        json={},
        headers=other_auth,
    )
    assert r.status_code == 404
    assert r.get_json()["error"] == "not found"
