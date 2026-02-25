"""Tests for multi-account financial overview dashboard."""


def _register(client, email, password="secret123"):
    client.post("/auth/register", json={"email": email, "password": password})


def _login(client, email, password="secret123"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.get_json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestAccountCRUD:
    def test_create_account(self, client):
        _register(client, "acct@test.com")
        token = _login(client, "acct@test.com")
        r = client.post(
            "/accounts",
            json={"name": "Main Checking", "account_type": "checking", "balance": 5000},
            headers=_auth(token),
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Main Checking"
        assert data["account_type"] == "checking"
        assert float(data["balance"]) == 5000

    def test_create_requires_valid_type(self, client):
        _register(client, "type@test.com")
        token = _login(client, "type@test.com")
        r = client.post(
            "/accounts",
            json={"name": "Bad", "account_type": "invalid"},
            headers=_auth(token),
        )
        assert r.status_code == 400

    def test_list_accounts(self, client):
        _register(client, "list@test.com")
        token = _login(client, "list@test.com")
        client.post("/accounts", json={"name": "A", "account_type": "checking"}, headers=_auth(token))
        client.post("/accounts", json={"name": "B", "account_type": "savings"}, headers=_auth(token))
        r = client.get("/accounts", headers=_auth(token))
        assert r.status_code == 200
        assert len(r.get_json()["accounts"]) == 2

    def test_get_account(self, client):
        _register(client, "get@test.com")
        token = _login(client, "get@test.com")
        r = client.post("/accounts", json={"name": "Test", "account_type": "cash", "balance": 100}, headers=_auth(token))
        aid = r.get_json()["id"]
        r = client.get(f"/accounts/{aid}", headers=_auth(token))
        assert r.status_code == 200
        assert r.get_json()["name"] == "Test"

    def test_update_account(self, client):
        _register(client, "upd@test.com")
        token = _login(client, "upd@test.com")
        r = client.post("/accounts", json={"name": "Old", "account_type": "checking"}, headers=_auth(token))
        aid = r.get_json()["id"]
        r = client.patch(f"/accounts/{aid}", json={"name": "New", "balance": 999}, headers=_auth(token))
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"
        assert float(r.get_json()["balance"]) == 999

    def test_delete_account(self, client):
        _register(client, "del@test.com")
        token = _login(client, "del@test.com")
        r = client.post("/accounts", json={"name": "Temp", "account_type": "cash"}, headers=_auth(token))
        aid = r.get_json()["id"]
        r = client.delete(f"/accounts/{aid}", headers=_auth(token))
        assert r.status_code == 200
        r = client.get(f"/accounts/{aid}", headers=_auth(token))
        assert r.status_code == 404

    def test_other_user_cannot_see_account(self, client):
        _register(client, "own@test.com")
        _register(client, "other@test.com")
        token1 = _login(client, "own@test.com")
        token2 = _login(client, "other@test.com")
        r = client.post("/accounts", json={"name": "Private", "account_type": "savings"}, headers=_auth(token1))
        aid = r.get_json()["id"]
        r = client.get(f"/accounts/{aid}", headers=_auth(token2))
        assert r.status_code == 404


class TestAccountOverview:
    def test_overview_totals(self, client):
        _register(client, "over@test.com")
        token = _login(client, "over@test.com")
        client.post("/accounts", json={"name": "Checking", "account_type": "checking", "balance": 3000}, headers=_auth(token))
        client.post("/accounts", json={"name": "Savings", "account_type": "savings", "balance": 7000}, headers=_auth(token))
        client.post("/accounts", json={"name": "Credit", "account_type": "credit", "balance": -500}, headers=_auth(token))

        r = client.get("/accounts/overview", headers=_auth(token))
        assert r.status_code == 200
        data = r.get_json()
        assert float(data["total_balance"]) == 9500.0
        assert data["account_count"] == 3
        assert "checking" in data["by_type"]
        assert "savings" in data["by_type"]

    def test_overview_excludes_inactive(self, client):
        _register(client, "inactive@test.com")
        token = _login(client, "inactive@test.com")
        r = client.post("/accounts", json={"name": "Active", "account_type": "checking", "balance": 1000}, headers=_auth(token))
        r2 = client.post("/accounts", json={"name": "Closed", "account_type": "savings", "balance": 500}, headers=_auth(token))
        aid = r2.get_json()["id"]
        client.patch(f"/accounts/{aid}", json={"is_active": False}, headers=_auth(token))

        r = client.get("/accounts/overview", headers=_auth(token))
        assert r.status_code == 200
        assert float(r.get_json()["total_balance"]) == 1000.0
        assert r.get_json()["account_count"] == 1


class TestTransfer:
    def test_transfer_between_accounts(self, client):
        _register(client, "xfer@test.com")
        token = _login(client, "xfer@test.com")
        r1 = client.post("/accounts", json={"name": "From", "account_type": "checking", "balance": 1000}, headers=_auth(token))
        r2 = client.post("/accounts", json={"name": "To", "account_type": "savings", "balance": 0}, headers=_auth(token))
        from_id = r1.get_json()["id"]
        to_id = r2.get_json()["id"]

        r = client.post(f"/accounts/{from_id}/transfer", json={"to_account_id": to_id, "amount": 250}, headers=_auth(token))
        assert r.status_code == 200
        data = r.get_json()
        assert float(data["from_account"]["balance"]) == 750
        assert float(data["to_account"]["balance"]) == 250

    def test_cannot_transfer_to_same_account(self, client):
        _register(client, "same@test.com")
        token = _login(client, "same@test.com")
        r = client.post("/accounts", json={"name": "Only", "account_type": "checking", "balance": 100}, headers=_auth(token))
        aid = r.get_json()["id"]
        r = client.post(f"/accounts/{aid}/transfer", json={"to_account_id": aid, "amount": 50}, headers=_auth(token))
        assert r.status_code == 400
