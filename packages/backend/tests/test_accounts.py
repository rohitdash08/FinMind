def test_accounts_crud_smoke(client, auth_header):
    r = client.post(
        "/accounts",
        json={
            "name": "Primary Checking",
            "account_type": "checking",
            "currency": "USD",
            "opening_balance": 1250.75,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    account = r.get_json()
    assert account["name"] == "Primary Checking"
    assert account["account_type"] == "CHECKING"
    assert account["opening_balance"] == 1250.75

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert any(item["id"] == account["id"] for item in r.get_json())

    r = client.patch(
        f"/accounts/{account['id']}",
        json={"name": "Everyday Checking", "opening_balance": 1300},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Everyday Checking"

    r = client.delete(f"/accounts/{account['id']}", headers=auth_header)
    assert r.status_code == 200
