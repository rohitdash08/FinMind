def test_accounts_crud_and_archive(client, auth_header):
    r = client.post(
        "/accounts",
        json={
            "name": "Main Checking",
            "account_type": "CHECKING",
            "institution": "Example Bank",
            "last_four": "1234",
            "currency": "USD",
            "opening_balance": 1000,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    account = r.get_json()
    account_id = account["id"]
    assert account["name"] == "Main Checking"
    assert account["account_type"] == "CHECKING"
    assert account["balance"] == 1000.0

    r = client.post(
        "/accounts",
        json={"name": "Main Checking", "account_type": "CHECKING"},
        headers=auth_header,
    )
    assert r.status_code == 409

    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Everyday Checking", "opening_balance": 1250},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Everyday Checking"
    assert updated["opening_balance"] == 1250.0

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert [a["name"] for a in r.get_json()] == ["Everyday Checking"]

    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    r = client.get("/accounts?include_archived=true", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()[0]["active"] is False


def test_accounts_are_scoped_to_authenticated_user(client, auth_header):
    r = client.post("/accounts", json={"name": "Private"}, headers=auth_header)
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    client.post(
        "/auth/register",
        json={"email": "other@example.com", "password": "password123"},
    )
    login = client.post(
        "/auth/login",
        json={"email": "other@example.com", "password": "password123"},
    )
    other_header = {"Authorization": f"Bearer {login.get_json()['access_token']}"}

    r = client.patch(
        f"/accounts/{account_id}", json={"name": "Stolen"}, headers=other_header
    )
    assert r.status_code == 404

    r = client.post(
        "/expenses",
        json={
            "amount": 10,
            "description": "Cross-account attempt",
            "date": "2026-02-01",
            "account_id": account_id,
        },
        headers=other_header,
    )
    assert r.status_code == 404
